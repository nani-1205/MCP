// cloud_webapp/static/js/main.js

// Connect to the Socket.IO server using the current window origin
const socket = io.connect(window.location.origin);

// Get references to UI elements
const agentStatusBadge = document.getElementById('agent-status-badge'); // Updated ID
const projectStatusMessages = document.getElementById('project-status-messages'); // Updated ID
const projectForm = document.getElementById('project-form'); // Updated ID (or keep if you added it)

/**
 * Updates the appearance and text of the agent status badge.
 * @param {string} status - The status string ('connected', 'disconnected', 'connecting', 'error').
 * @param {string} message - The text message to display.
 */
function updateAgentStatusUI(status, message) {
    if (!agentStatusBadge) return; // Exit if element not found

    // Set default class
    agentStatusBadge.className = 'status-badge'; // Reset classes first

    switch (status) {
        case 'connected':
            agentStatusBadge.classList.add('connected');
            break;
        case 'connecting': // Handle intermediate state
            agentStatusBadge.classList.add('connecting');
            break;
        case 'error': // Explicit error state
            agentStatusBadge.classList.add('disconnected'); // Use disconnected style for error too
            break;
        case 'disconnected':
        default:
            agentStatusBadge.classList.add('disconnected');
            break;
    }
    agentStatusBadge.textContent = `Agent Status: ${message}`;
}


/**
 * Handles the initial connection event from Socket.IO.
 * Emits 'join_user_room' to the server.
 */
socket.on('connect', () => {
    console.log('Browser connected to MCP server with SID:', socket.id);
    socket.emit('join_user_room');
    console.log('Emitted join_user_room request.');
    // Set initial UI status
    updateAgentStatusUI('connecting', 'Checking...');
});

/**
 * Handles the disconnection event. Updates UI.
 */
socket.on('disconnect', (reason) => {
    console.log('Browser disconnected from MCP server:', reason);
    updateAgentStatusUI('disconnected', 'Server Disconnected');
});

/**
 * Handles connection errors. Updates UI.
 */
socket.on('connect_error', (error) => {
    console.error('Browser connection error:', error);
    updateAgentStatusUI('error', 'Connection Error');
});


/**
 * Listens for 'agent_status' events from the server. Updates UI.
 */
socket.on('agent_status', (data) => {
    console.log('Agent Status Update Received:', data);
    updateAgentStatusUI(data.status, data.message);
});

/**
 * Listens for 'project_status' events from the server. Displays messages.
 */
socket.on('project_status', (data) => {
    console.log('Project Status Update Received:', data);
    if (projectStatusMessages) { // Ensure the element exists
        const statusMsg = `[${new Date().toLocaleTimeString()}] ${data.status}: ${data.message}`;
        const p = document.createElement('p');
        p.textContent = statusMsg;
        // Apply basic styling based on status
        if (data.status === 'error') {
            p.style.color = 'var(--danger)'; // Use CSS variable
            p.style.fontWeight = 'bold';
        } else if (data.status === 'success') {
            p.style.color = 'var(--success)'; // Use CSS variable
        } else if (data.status === 'pending') {
             p.style.fontStyle = 'italic';
             p.style.color = 'var(--text-light)'; // Use CSS variable
        }
        // Prepend new status message to keep the latest at the top
        projectStatusMessages.insertBefore(p, projectStatusMessages.firstChild);
        // Scroll to top of status message area
        projectStatusMessages.scrollTop = 0;
    } else {
        console.error('project-status-messages div not found in the DOM');
    }
});

/**
 * Adds submit listener to the project form.
 */
if (projectForm) { // Ensure the form exists
    projectForm.addEventListener('submit', (event) => {
        event.preventDefault(); // Prevent standard form submission

        // Get values from form fields (use the correct IDs from the new HTML)
        const projectNameInput = document.getElementById('projectName');
        const projectTypeInput = document.getElementById('projectType');
        const basePathInput = document.getElementById('basePath');

        if (!projectNameInput || !projectTypeInput || !basePathInput) {
             console.error('One or more form elements not found!');
             alert('Form elements are missing. Cannot proceed.');
             return;
        }

        const projectName = projectNameInput.value.trim();
        const projectType = projectTypeInput.value; // Get selected value
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
        p.style.color = 'var(--text-light)';
        if (projectStatusMessages) {
             projectStatusMessages.insertBefore(p, projectStatusMessages.firstChild);
             projectStatusMessages.scrollTop = 0;
        }

        // Send the request details to the server via Socket.IO
        socket.emit('create_project_request', {
            projectName: projectName,
            projectType: projectType, // Use the value from the select dropdown
            basePath: basePath
        });
    });
} else {
    console.error('project-form not found in the DOM');
}

console.log("MCP main.js loaded.");