import requests, time
print("Starting...")
requests.post('http://127.0.0.1:5000/api/start')
for i in range(10):
    time.sleep(1)
    res = requests.get('http://127.0.0.1:5000/api/state').json()
    print("Tick:", res.get("tick"))
