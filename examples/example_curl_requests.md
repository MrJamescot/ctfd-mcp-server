# Example CURL requests

Set token:
curl -X POST "http://localhost:9999/api/v1/set_token" -H "Content-Type: application/json" -d '{"token":"YOUR_TOKEN_HERE"}'

List challenges:
curl "http://localhost:9999/api/v1/challenges"

Get challenge:
curl "http://localhost:9999/api/v1/challenges/1"

Download file:
curl "http://localhost:9999/api/v1/files/12" -o file_12.bin

Submit flag:
curl -X POST "http://localhost:9999/api/v1/submit" -H "Content-Type: application/json" -d '{"challenge_id":1,"flag":"flag{test}"}'
