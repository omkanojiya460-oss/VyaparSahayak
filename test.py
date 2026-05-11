import requests

response = requests.post(
    "https://vyaparsahayak.onrender.com/chat",
    json={"message": "50 kg aata becha 35 rupaye kilo Ramesh ko"}
)

print("Status:", response.status_code)
print("Response:", response.text)