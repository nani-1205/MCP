
# My Cloud Project (MCP)

## Overview

My Cloud Project (MCP) is a system designed to allow users to create development project structures on their local machine remotely via a cloud-hosted web interface. It consists of two main components:

1.  **Cloud Web Application:** A Flask/SocketIO web server typically hosted on a cloud platform (like Google Cloud Run, AWS, Azure, etc.). It provides the user interface, handles user sessions, manages authentication tokens, and communicates with the Local Agent.
2.  **Local Agent:** A Python script that runs on the user's local development machine. It securely connects to the Cloud Web Application via WebSockets, listens for project creation commands, and executes file/directory operations locally based on predefined templates.

**Note:** This architecture is necessary because web browsers are sandboxed and cannot directly access or modify the local file system for security reasons. The Local Agent acts as a trusted intermediary controlled by the user.

## Architecture

```text
+-------------------+      (HTTPS/WSS)      +-------------------------+      (WebSocket WSS)     +------------------+
| User's Browser    | <-------------------> | Cloud Web Application   | <----------------------> | Local Agent      |
| (Web UI via HTTP) |                       | (Flask/SocketIO Server) |                          | (Python Script)  |
+-------------------+                       | - Handles UI            |                          +--------+---------+
                                            | - User Sessions/Auth    |                                   |
                                            | - Manages Agent Tokens  |                                   | (File System Ops)
                                            | - Relays Commands       |                                   V
                                            | - Hosted on Cloud       |                          +------------------+
                                            +-------------------------+                          | Local PC         |
                                                                                                 | File System      |
                                                                                                 +------------------+
## Features

*   Web-based interface for triggering project creation.
*   Real-time communication via WebSockets.
*   Local agent performs actions on the user's machine.
*   Basic project template support (Python, Node.js - expandable).
*   Separation between cloud control plane and local execution.

## Prerequisites

**Cloud Web Application:**

*   Python 3.x
*   `pip` (Python package installer)
*   Git (for cloning)
*   A cloud hosting provider (e.g., Google Cloud, AWS, Azure) or a server capable of running Python web applications.
*   (Optional but Recommended for Cloud) Docker

**Local Agent:**

*   Python 3.x
*   `pip`
*   Git (if using templates that require it)
*   Any tools required by specific project templates (e.g., Node.js/npm for Node projects)

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd mcp-project
    ```

2.  **Setup Cloud Web Application (`cloud_webapp`):**
    ```bash
    cd cloud_webapp

    # Create and activate a virtual environment (recommended)
    python -m venv venv
    # Windows: venv\Scripts\activate
    # macOS/Linux: source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt

    # Set necessary environment variables (especially for production)
    # Example (Linux/macOS): export FLASK_SECRET_KEY='your_very_strong_random_secret_key'
    # Example (Windows Cmd): set FLASK_SECRET_KEY=your_very_strong_random_secret_key
    # Example (Windows PowerShell): $env:FLASK_SECRET_KEY="your_very_strong_random_secret_key"
    # (Use a Secret Manager in production!)
    ```
    *   For cloud deployment, refer to your provider's documentation (e.g., deploying a container to Cloud Run, setting up Gunicorn + Eventlet).

3.  **Setup Local Agent (`local_agent`):**
    ```bash
    cd ../local_agent # Go back to root and into local_agent

    # Create and activate a separate virtual environment (recommended)
    python -m venv venv
    # Windows: venv\Scripts\activate
    # macOS/Linux: source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    ```

## Configuration

The **Local Agent** requires configuration via the `local_agent/config.yaml` file. Create this file if it doesn't exist:

```yaml
# local_agent/config.yaml

# URL where the Cloud Web App is running (e.g., http://your-cloud-app-url.com or http://localhost:5000 for local dev)
cloud_url: 'http://18.61.85.248:5000' # <-- CHANGE THIS

# --- Authentication ---
# Get these details by visiting the /get_agent_token endpoint on your running Cloud Web App
user_id: 'user_...' # <-- CHANGE THIS
agent_token: 'agent_token_...' # <-- CHANGE THIS

# --- !! IMPORTANT !! ---
# The base directory on THIS local PC where new projects will be created.
# The agent WILL CREATE FOLDERS AND FILES here based on commands from the web app.
# Ensure this path exists or is creatable by the user running the agent.
# Use forward slashes (/) even on Windows.
base_dev_path: 'C:/Users/your_username/Documents/Development' # <-- CHANGE THIS TO YOUR SAFE DEV FOLDER
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

Steps to get user_id and agent_token:

Run the Cloud Web Application (see next section).

Open your browser and navigate to http://<your-cloud-app-url>/get_agent_token.

Copy the user_id and agent_token values shown in the JSON response.

Paste these values into your local_agent/config.yaml.

Crucially, update base_dev_path to a real, safe directory on your computer where you want projects created.

Running the Application

You need two terminals running simultaneously: one for the cloud app and one for the local agent.

Run the Cloud Web Application:

Navigate to the cloud_webapp directory.

Activate its virtual environment.

Ensure FLASK_SECRET_KEY is set.

Development: python app.py

Production (Example using Gunicorn): gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:8080 app:app (Adjust host/port/workers as needed for your deployment).

Production (Example using PM2 on server): pm2 start app.py --name mcp-app --interpreter python3 -- --worker-class eventlet -w 1 (Adapt interpreter/args if not using gunicorn within app.py's socketio.run)

Run the Local Agent:

Navigate to the local_agent directory.

Activate its virtual environment.

Ensure config.yaml is correctly configured.

Run: python agent.py

Keep this terminal running. For continuous operation, consider running it as a background service (systemd, launchd, Task Scheduler).

Usage

Ensure both the Cloud Web Application and the Local Agent are running.

If this is the first time or your credentials might be invalid, visit http://<your-cloud-app-url>/get_agent_token in your browser.

Update local_agent/config.yaml if you received new credentials and restart the Local Agent. Wait for the agent terminal to show successful authentication.

Navigate to the main web UI at http://<your-cloud-app-url>/.

The "Agent Status" should update to show "connected" or similar.

Fill in the form:

Project Name: The desired name for your new project folder (e.g., my-new-api).

Project Type: Select a template (e.g., Python Basic).

Base Path on your PC: Enter the exact same path as your base_dev_path configured in the agent's config.yaml (e.g., C:/Users/your_username/Documents/Development). The agent will create the Project Name folder inside this path.

Click "Create Project".

Observe the status messages in the web UI and check your local file system at the specified path for the newly created project folder.

Security Considerations - VERY IMPORTANT!

Risk: The Local Agent executes commands and modifies files on your local machine based on instructions received from the Cloud Web Application. Granting any remote access to your local system carries inherent security risks. Use this system with extreme caution.

Agent Permissions: The agent runs with the permissions of the user who started it. It can potentially do anything that user can do.

Authentication: The current token system (/get_agent_token and in-memory storage) is NOT SECURE for production. It's vulnerable and tokens don't expire. Implement a robust user authentication system (e.g., OAuth, proper password hashing with Flask-Login) and secure, database-backed storage for agent tokens with expiration/revocation capabilities.

Encryption: Communication between the browser, cloud app, and agent MUST use HTTPS/WSS in production to prevent eavesdropping.

Path Validation (base_dev_path): The agent performs checks to ensure requested project creation paths are within the configured base_dev_path. Do NOT misconfigure base_dev_path to sensitive system locations. Ensure the validation logic in agent.py is robust.

Input Sanitization: Project names and types received from the web UI should be strictly validated on the server and/or agent to prevent path traversal attacks or unexpected behavior.

Command Execution: Avoid features that allow arbitrary command execution. Stick to predefined, parameterized actions (like creating files from known templates, running specific safe commands like git init).

Cloud App Security: Secure the Cloud Web Application itself against common web vulnerabilities (XSS, CSRF, etc.). Control who can access the application.

