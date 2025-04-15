// cloud_webapp/static/js/main.js

// Connect to the Socket.IO server using the current window origin
// This assumes Flask and SocketIO are served from the same host/port
// If they are different in production, specify the full URL: io.connect('https://yourserver.com')
const socket = io.connect(window.location.origin);

// Get references to UI elements
const agentStatusDiv = document.getElementById('agent-status');
const projectStatusDiv = document.getElementById('project-status');
const projectForm = document.getElementById('project-form');

/**
 * Handles the initial connection event from Socket.IO.
 * Emits 'join_user_room' to the server to link this browser
 * session with the user's room for receiving broadcasts.
 */
socket.on('connect', () => {
    console.log('Browser connected to MCP server with SID:', socket.id);
    // Tell the server to add this browser connection to the user's room.
    // The server uses the Flask session cookie (sent automatically) to identify the user.
    socket.emit('join_user_room');
    console.log('Emitted join_user_room request.');
    // Set initial status until an update is received from the server
    agentStatusDiv.textContent = 'Agent Status: Checking...';
    agentStatusDiv.style.color = 'orange';
});

/**
 * Handles the disconnection event.
 * Updates the UI to show disconnection status.
 * @param {string} reason - The reason for disconnection.
 */
socket.on('disconnect', (reason) => {
    console.log('Browser disconnected from MCP server:', reason);
    agentStatusDiv.textContent = 'Agent Status: Server Disconnected';
    agentStatusDiv.style.color = 'red';
});

/**
 * Handles connection errors.
 * Updates the UI to show an error state.
 * @param {object} error - The connection error object.
 */
socket.on('connect_error', (error) => {
    console.error('Browser connection error:', error);
    agentStatusDiv.textContent = 'Agent Status: Connection Error';
    agentStatusDiv.style.color = 'red';
});


/**
 * Listens for 'agent_status' events broadcasted by the server
 * (typically when an agent connects/disconnects or upon joining the room).
 * Updates the agent status display in the UI.
 * @param {object} data - The status data from the server.
 * @param {string} data.status - 'connected', 'disconnected', 'error', etc.
 * @param {string} data.message - The status message to display.
 */
socket.on('agent_status', (data) => {
    console.log('Agent Status Update Received:', data);
    if (agentStatusDiv) { // Ensure the element exists
        agentStatusDiv.textContent = `Agent Status: ${data.message}`;
        agentStatusDiv.style.color = (data.status === 'connected') ? 'green' : 'orange';
        // Handle specific error cases if needed
        if (data.status === 'error') {
             agentStatusDiv.style.color = 'red';
        }
    } else {
        console.error('agent-status div not found in the DOM');
    }
});

/**
 * Listens for 'project_status' events sent by the server during
 * project creation attempts or when the agent sends back a response.
 * Displays the status message in the project status area.
 * @param {object} data - The status data from the server.
 * @param {string} data.status - 'pending', 'success', 'error', etc.
 * @param {string} data.message - The status message to display.
 */
socket.on('project_status', (data) => {
    console.log('Project Status Update Received:', data);
    if (projectStatusDiv) { // Ensure the element exists
        const statusMsg = `[${new Date().toLocaleTimeString()}] ${data.status}: ${data.message}`;
        const p = document.createElement('p');
        p.textContent = statusMsg;
        // Apply basic styling based on status
        if (data.status === 'error') {
            p.style.color = 'red';
            p.style.fontWeight = 'bold';
        } else if (data.status === 'success') {
            p.style.color = 'green';
        } else if (data.status === 'pending') {
             p.style.fontStyle = 'italic';
        }
        // Prepend new status message to keep the latest at the top
        projectStatusDiv.insertBefore(p, projectStatusDiv.firstChild);
    } else {
        console.error('project-status div not found in the DOM');
    }
});

/**
 * Adds an event listener to the project creation form.
 * Prevents default form submission, validates inputs,
 * and emits the 'create_project_request' event to the server via Socket.IO.
 */
if (projectForm) { // Ensure the form exists
    projectForm.addEventListener('submit', (event) => {
        event.preventDefault(); // Prevent standard form submission

        // Get values from form fields
        const projectNameInput = document.getElementById('projectName');
        const projectTypeInput = document.getElementById('projectType');
        const basePathInput = document.getElementById('basePath');

        // Simple validation
        if (!projectNameInput || !projectTypeInput || !basePathInput) {
             console.error('One or more form elements not found!');
             alert('Form elements are missing. Cannot proceed.');
             return;
        }

        const projectName = projectNameInput.value.trim();
        const projectType = projectTypeInput.value;
        const basePath = basePathInput.value.trim();

        if (!projectName || !projectType || !basePath) {
            alert('Please fill in all fields.');
            return;
        }

        console.log(`Requesting project creation: Name='${projectName}', Type='${projectType}', Path='${basePath}'`);

        // Display immediate feedback in the status area
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] pending: Sending request for '${projectName}'...`;
        p.style.fontStyle = 'italic';
        if (projectStatusDiv) {
             projectStatusDiv.insertBefore(p, projectStatusDiv.firstChild);
        }

        // Send the request details to the server via Socket.IO
        // This request goes over the browser's established socket connection.
        socket.emit('create_project_request', {
            projectName: projectName,
            projectType: projectType,
            basePath: basePath
        });
    });
} else {
    console.error('project-form not found in the DOM');
}

// --- Optional: Add a button/logic to manually request agent status ---
// This would require adding a button with id="check-agent-status-button" to index.html
// and adding a corresponding @socketio.on('request_agent_status') handler on the backend.
/*
const checkStatusButton = document.getElementById('check-agent-status-button');
if (checkStatusButton) {
    checkStatusButton.addEventListener('click', () => {
        console.log('Requesting agent status check...');
        if (socket.connected) {
            socket.emit('request_agent_status');
             // Provide immediate feedback
             agentStatusDiv.textContent = 'Agent Status: Requesting update...';
             agentStatusDiv.style.color = 'orange';
        } else {
             console.error('Cannot request status, socket not connected.');
             agentStatusDiv.textContent = 'Agent Status: Server Disconnected';
             agentStatusDiv.style.color = 'red';
        }
    });
}
*/

console.log("MCP main.js loaded.");