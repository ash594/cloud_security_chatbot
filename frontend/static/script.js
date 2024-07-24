document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.getElementById('chat-container');
    const helpButton = document.getElementById('help-button');
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    helpButton.addEventListener('click', function() {
        if (chatContainer.style.display === 'none' || chatContainer.style.display === '') {
            chatContainer.style.display = 'flex';
            initializeChat();
        } else {
            chatContainer.style.display = 'none';
        }
    });

    sendButton.addEventListener('click', function() {
        const query = userInput.value.trim();
        if (query !== '') {
            addMessage(query, 'visitor-message');
            userInput.value = '';
            fetchResponse(query);
        }
    });

    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendButton.click();
        }
    });

    function addMessage(message, className) {
        const messageContainer = document.createElement('div');
        messageContainer.className = 'chat-message';
    
        const messageElement = document.createElement('div');
        messageElement.className = className;
        messageElement.innerHTML = message;
    
        messageContainer.appendChild(messageElement);
    
        // Add the new message
        chatBox.appendChild(messageContainer);
    
        // Scroll to the top of the new message
        const scrollPosition = chatBox.scrollTop + messageContainer.getBoundingClientRect().top - chatBox.getBoundingClientRect().top;
        chatBox.scrollTop = scrollPosition;
    }    

    function fetchResponse(query) {
        fetch('http://127.0.0.1:5000/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query: query })
        })
        .then(response => response.json())
        .then(data => {
            addMessage(data.message, 'bot-message');
        })
        .catch(error => {
            console.error('Error:', error);
            addMessage('An error occurred. Please try again.', 'bot-message');
        });
    }

    function initializeChat() {
        if (chatBox.children.length === 0) {
            fetch('http://127.0.0.1:5000/welcome', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                addMessage(data.message, 'bot-message');
            })
            .catch(error => {
                console.error('Error:', error);
                addMessage('An error occurred. Please try again.', 'bot-message');
            });
        }
    }
});