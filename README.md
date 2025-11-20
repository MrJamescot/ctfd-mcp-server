# CTFd MCP Server

A lightweight and extensible Model Context Protocol (MCP) server for interacting with any CTFd instance.
This project enables AI tools and automation to authenticate, retrieve challenges, and submit flags through a stable API layer.
## Overview
This project acts as a bridge between CTFd and AI-driven systems by providing a unified interface.
It supports multiple authentication modes, dynamic base URL control, and FastAPI endpoints for debugging and integration.

The server is validated using the official demo instance at https://demo.ctfd.io.




## Features

- Dynamic BASE_URL configuration
- Token and cookie authentication
- Username/password login
- List challenges with optional filtering
- Submit flags programmatically
- Compatible with MCP-based AI tools
- Clean and extensible Python codebase

## Installation

Install the MCP server using Python:
```bash
git clone https://github.com/YourUser/ctfd-mcp-server.git
cd ctfd-mcp-server
pip install -r requirements.txt
```
Create your environment configuration:

```bash
cp .env.example .env

```
Edit .env as needed:

```bash
BASE_URL=https://demo.ctfd.id
CTFD_TOKEN=
CTFD_COOKIE=
```


    
## Running the MCP Server

Start the server with Python:
```bash
python mcp_server.py
```
The default FastAPI server runs at:
```bash
http://127.0.0.1:8000
```

    
## Example MCP Configuration

If you are using a client such as Claude Desktop or a compatible MCP host, configure it as follows:
```javascript
{
  "mcpServers": {
    "ctfd-mcp": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "BASE_URL": "https://demo.ctfd.io"
      }
    }
  }
}

```

    
## Usage/Examples
Set Token
```javascript
{
  "method": "set_token",
  "params": { "token": "your_token_here" }
}
```
Get Challanges
```javascript
{
  "method": "challenges",
  "params": {}
}
```
Sumbit Flag
```javascript
{
  "method": "submit_flag",
  "params": {
    "challenge_id": 3,
    "flag": "flag{example_payload}"
  }
}

```





## API Endpoints (FastAPI)

| Method | Path               | Description              |
| ------ | ------------------ | ------------------------ |
| POST   | /set_token         | Set authentication token |
| POST   | /set_cookie        | Set session cookie       |
| POST   | /login             | Login with credentials   |
| GET    | /api/v1/challenges | Retrieve challenges      |
| POST   | /api/v1/flags      | Submit a flag            |









## Support

For support, email jamescotid@gmail.com
 or open an issue through the GitHub repository.
Community contributions and improvements are always welcome.

## License

[MIT](https://github.com/MrJamescot/ctfd-mcp-server/blob/main/LICENSE)

