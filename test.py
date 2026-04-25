import requests

response = requests.post(
    "http://127.0.0.1:5000/chat",
    json={"message": "50 kg aata becha 35 rupaye kilo Ramesh ko"}
)

print("Status:", response.status_code)
print("Response:", response.text)