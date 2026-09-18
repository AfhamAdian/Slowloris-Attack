# Slowloris DoS Attack: Demonstration and Defense — Project Design

Cybersecurity Sessional project. Goal: sandbox a Slowloris attack against a real web server, show it denies service to legitimate users, then show a server side fix defeats it.

## 1. The Concept

Slowloris is a Layer 7 (application layer) denial of service attack. It sends almost no data and never floods the network. It exploits a specific assumption: once a client starts sending an HTTP request, the server assumes it will finish sending it in a reasonable amount of time.

A threaded or process per connection web server assigns one worker to each open connection and holds that worker reserved until the request is fully received. A request counts as complete only once the header section ends with a blank line, meaning the byte sequence `\r\n\r\n`.

Slowloris opens many connections to the server and, on each one, sends a single valid header line, waits a few seconds, then sends another valid header line, forever, never sending the terminating blank line. Each line is syntactically fine on its own, so the server treats it as a slow but legitimate client still sending its request rather than something to reject. As long as each send arrives before the server's idle timer expires, that timer resets and the worker stays reserved. Doing this on enough connections at once ties up the server's entire worker pool with requests that will never finish, so it can no longer accept connections from real users.

The core condition that keeps the attack alive:

$$\Delta t_{\text{send}} < T_{\text{server timeout}}$$

As long as this holds on every connection, no worker is ever released. The defense in Section 7 works by capping how far this can be exploited, regardless of how well timed the attacker's sends are.

Two things this project needs to prove:
1. A small number of slow connections from a resource limited attacker can deny service to legitimate clients, measured by legitimate request success rate and response latency.
2. An absolute header receive timeout that cannot be reset indefinitely defeats the attack.

## 2. Why Apache, Not an Event Driven Server (Express, nginx)

What actually determines vulnerability to this attack is not the server software's brand, it's how it handles a connection while it waits for more data.

Apache configured in prefork mode assigns one whole worker process to each connection, and that process sits blocked, doing nothing else, until the request finishes or times out. With a small fixed worker pool, e.g. 20 to 50 workers, a matching number of slow connections ties up every worker and nothing is left for real users. This gives a clean, observable rise to the limit and plateau within a short lab session, and Apache ships the exact tools needed: `mod_status` to watch worker counts live, and `mod_reqtimeout` to fix the vulnerability.

Express (Node) and nginx use a different model: one thread (or a few) driven by an event loop, watching many connections at once without dedicating a blocked worker to each. A connection sitting idle, waiting for more header data, costs almost nothing while it waits. There is no small pool of blocked workers to exhaust, so the classic Slowloris effect largely does not reproduce there. This is why nginx is the standard "unaffected" counterexample in Slowloris write ups, and it is why Apache prefork is the standard target.

Note for the report: Express is not immune to every resource exhaustion idea, things like max connections, memory per socket, or file descriptor limits can still be attacked (e.g. slow POST body attacks), but the specific mechanism here, exhausting a small dedicated worker pool, needs a server that actually has one. A good optional side experiment: run the same attacker script against an Express server and show it does not degrade the same way, as a direct demonstration of this reasoning.

## 3. Lab Topology

Four machines (VMs or containers) on one isolated private network, no external traffic:

1. **Attacker node**: opens $N$ concurrent sockets to the server, sends one incomplete header line per socket on each pass, spaced under the server's timeout.
2. **Legitimate client**: issues normal, complete HTTP requests at a steady rate for the whole run. Its success rate and response time are the measured impact.
3. **Target web server**: Apache, prefork MPM, small fixed worker pool.
4. **Monitor**: logs the server's active worker count and open connection count over time. Can run on the server host itself or as a separate logger.

For the defense stage, a reverse proxy or timeout module sits in front of the server enforcing the fix before traffic reaches the worker pool (or the fix is applied directly on the Apache config, which is the simpler path for this project).

## 4. Apache Setup and How It Works

Apache is the web server under attack. Configure it with the **prefork MPM**: it starts a fixed number of worker processes ahead of time, each one idle until handed a connection, and each stays tied to that connection until the request completes or times out.

Config points:
* `MaxRequestWorkers` (or `MaxClients` on older Apache) set low, e.g. 20 to 50, so exhaustion is reachable in minutes without needing thousands of connections.
* `mod_status` enabled, exposing a live status page (commonly at `/server-status`) with `BusyWorkers` and `IdleWorkers` fields. This is what the monitor polls.
* For the defense stage: `mod_reqtimeout` enabled (see Section 7).

This is a deliberately vulnerable lab configuration chosen to make the effect observable quickly, not a claim about typical production defaults.

## 5. Monitor Setup

A small script, run on a timer (e.g. every 2 seconds), that logs two things with a timestamp on each pass:

1. **Worker utilization**: fetch the Apache status page (`mod_status`) and parse out `BusyWorkers` and `IdleWorkers`.
2. **Open connection count**: run `ss -tn` filtered to the server's port (e.g. port 80) and count the lines, or parse the actual connection count.

Also log server host **CPU and memory usage** over the same timer, expected to stay near idle throughout, which is the point that distinguishes this from a volumetric flood.

Output: a simple timestamped log file (CSV or similar) with columns like `time, busy_workers, idle_workers, open_connections, cpu_pct, mem_pct`. This becomes the main results graph: worker/connection count rising to a plateau while resource usage stays flat.

## 6. Attacker

A Python script (e.g. `attacker.py`), run directly with `python3 attacker.py` from the attacker machine. No packaging needed. Uses raw sockets.

Structure:
* Open $N$ sockets up front (start around $N = 200$, adjustable).
* On each socket, immediately send a request line and a `Host` header, so it looks like a normal request has started.
* Loop forever: on each pass, send one more small, valid header line to every open socket, then sleep for `INTERVAL` seconds (comfortably under the server's timeout, start around 10 seconds).
* Never send the terminating blank line (`\r\n\r\n`) on any socket.
* Detect and reopen any socket the server drops, so $N$ stays roughly constant across the run.

Reference pseudocode (from the design doc, to be turned into working Python):

```python
N = 200                          # number of concurrent sockets
INTERVAL = 10                    # seconds between header sends, < server timeout

sockets = []
for i in range(N):
    s = connect(server_ip, 80)
    send(s, "GET /?" + random_string() + " HTTP/1.1\r\n")
    send(s, "Host: target\r\n")
    sockets.append(s)

while True:
    for s in sockets:
        if s.is_connected():
            send(s, "X-" + random_header_name() + ": " + random_value() + "\r\n")
        else:
            s = reconnect_and_resend_initial_lines(server_ip, 80)
    sleep(INTERVAL)
```

## 7. Legitimate Client

Role: stand in for a real user trying to use the site while the attack (or defense) is running. This is what turns the result from "internal server numbers changed" into "real users were denied service," the actual claim being tested. It runs unchanged through every phase, baseline, attack, and defense, so any change in its numbers is caused by the server's state, not by anything the client itself does differently.

What it does: a script, on its own machine, looping forever. Each iteration sends one complete, ordinary HTTP request, waits for a response or a timeout, logs the outcome, sleeps a fixed short interval (e.g. 1 second), repeats.

Reference pseudocode:

```python
RATE = 1                         # one request every second

while experiment_running:
    t0 = now()
    try:
        response = http_get(server_ip, "/", timeout=5)
        log(t0, status="success", latency=now() - t0, code=response.status_code)
    except TimeoutOrConnectionError:
        log(t0, status="failure", latency=None)
    sleep(RATE)
```

**Metrics measured from the client, per request:**
* success / failure / timeout outcome
* response time (latency), from send to response

**Derived, in time windows, for the graphs:**
* success rate (%) over time — near 100% at baseline, collapses during attack, should recover close to baseline once defense is applied
* average response time over time — low and flat at baseline, spikes or hits timeout levels during attack, should return close to baseline with defense applied

This client's data is the strongest evidence in the report: it is the direct, user visible proof of denial of service, not just an internal server metric.

## 8. Measurements Summary

**On the server (undefended and defended runs, same metrics both times):**
* active worker count over time (from `mod_status`)
* open connection count over time (from `ss -tn`)
* CPU and memory usage over time (expected to stay low throughout, both runs)
* time from attack start to worker pool saturation (undefended run)
* whether/how far worker count rises and how fast it recovers (defended run)

**On the legitimate client (all phases):**
* per request outcome (success/failure/timeout)
* per request response time
* derived success rate (%) over time
* derived average response time over time

## 9. Test Procedure

1. **Baseline**: legitimate client only, no attacker, for a few minutes. Confirms ~100% success rate and stable low latency. Screenshot as the "before" reference.
2. **Attack**: start the legitimate client, then start the attacker with chosen $N$. Run until the worker pool saturates or for a fixed duration. Screenshot start, middle, and the point it flattens out.
3. **Recovery** (proves causation): stop the attacker, show the client's success rate returns to baseline on its own, without restarting anything else.
4. **Sweep** (optional, strengthens the report): repeat the attack at a few values of $N$ (e.g. 50, 100, 200) and compare how quickly saturation happens as $N$ approaches the worker pool limit.
5. **Defense**: apply the fix (Section 10), repeat the identical attack run unchanged. Client success rate should stay close to baseline this time.

**Screens/evidence to capture per phase (attacker, victim/server, client), as required by the assignment:**
* Attacker terminal: showing connection count and that headers are sent without ever completing a request.
* Server: `mod_status` output or the logged graph, worker count climbing to max and plateauing (undefended) vs staying near baseline (defended); also a plain browser request from the client machine, hanging/timing out during attack vs loading normally before/after and under defense.
* Client: request log turning from successes into timeouts, plus the success rate / response time graphs, undefended vs defended.

## 10. Expected Results

**Undefended attack**, successful if it reproduces both effects without saturating CPU or memory:
* worker count climbs from idle baseline to `MaxRequestWorkers` and plateaus, within roughly one attacker cycle interval of reaching that size
* legitimate success rate starts near 100%, drops substantially as the pool saturates, latency rises and becomes inconsistent, may approach zero with large enough $N$
* CPU/memory stay near idle the whole time — the key contrast that shows this is a connection exhaustion attack, not a volumetric one

**Defended run**, same attacker script and same $N$:
* attacker connections get closed once the bounded header timeout window elapses
* active worker utilization stays near baseline instead of climbing to the pool limit
* legitimate client success rate stays close to baseline throughout

## 11. Defense

**Primary fix: bounded request header timeout.** The root cause is that a plain idle timer is freely resettable, any incoming byte restarts the clock with no cap on how many times this can happen. The fix puts a finite upper bound on how far the timer can be extended, so an attacker sending data just fast enough to dodge the idle timeout still cannot stall a request indefinitely.

On Apache, via `mod_reqtimeout`:

```
RequestReadTimeout header=10-20,MinRate=500
RequestReadTimeout body=20,MinRate=500
```

Each stage starts with a base timeout (10 seconds for headers) and extends per incoming data at the configured minimum rate (`MinRate`, bytes/second), capped at the second value (20 seconds for headers). This is a bounded, adaptive timeout, not a fixed deadline set once at connection start: a genuinely slow client trickling data still gets extra time, but not indefinitely. Under this, satisfying $\Delta t_{\text{send}} < T_{\text{server timeout}}$ on every send is no longer sufficient on its own, the header stage must still complete within the bounded window or the connection is closed and the worker freed.

**Secondary fix: per source concurrent connection limiting.** Cap how many connections a single source IP may hold open at the same time (via `mod_qos`, a firewall connection tracking rule, or a reverse proxy). This is a concurrency cap, not a rate limit, it does not restrict how often a client connects, only how many connections it may hold open at once. Since Slowloris's leverage comes from one or a few hosts occupying a large share of a small worker pool, this forces a single host attacker to acquire many more source addresses to have the same effect, raising the cost of the attack independent of the timeout fix.
