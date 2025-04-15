// Connect to the Socket.IO server (adjust URL for production)
const socket = io.connect('http://' + document.domain + ':' + location.port); // Assumes Flask runs on same host/port

const agentStatusDiv = document.getElementById('agent-status');
const projectStatusDiv = document.getElementById('project-status');
const projectForm = document.getElementById('project-form');

socket.on('connect', () => {
    console.log('Connected to MCP server');
    // // Authentication with server (if browser session needs SocketIO link)
    // // This might be handled by Flask session cookies automatically
    // socket.emit('authenticate_browser', { user_id: 'get_user_id_somehow' });
});

socket.on('disconnect', () => {
    console.log('Disconnected from MCP server');
    agentStatusDiv.textContent = 'Agent Status: Server Disconnected';
    agentStatusDiv.style.color = 'red';
});

socket.on('agent_status', (data) => {
    console.log('Agent Status Update:', data);
    agentStatusDiv.textContent = `Agent Status: ${data.message}`;
    agentStatusDiv.style.color = (data.status === 'connected') ? 'green' : 'orange';
});

socket.on('project_status', (data) => {
    console.log('Project Status Update:', data);
    const statusMsg = `[${new Date().toLocaleTimeString()}] ${data.status}: ${data.message}`;
    const p = document.createElement('p');
    p.textContent = statusMsg;
    projectStatusDiv.appendChild(p);
    // Auto-scroll maybe
    projectStatusDiv.scrollTop = projectStatusDiv.scrollHeight;
});


projectForm.addEventListener('submit', (event) => {
    event.preventDefault();
    projectStatusDiv.innerHTML = ''; // Clear previous status

    const projectName = document.getElementById('projectName').value;
    const projectType = document.getElementById('projectType').value;
    const basePath = document.getElementById('basePath').value;

    if (!projectName || !projectType || !basePath) {
        alert('Please fill in all fields.');
        return;
    }

    console.log(`Requesting project creation: ${projectName}, ${projectType}, ${basePath}`);
    projectStatusDiv.textContent = 'Sending request to server...';

    // Send request to server via Socket.IO
    socket.emit('create_project_request', {
        projectName: projectName,
        projectType: projectType,
        basePath: basePath
    });
});

// Initial check or status request could go here if needed