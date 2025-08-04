document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const messagesContainer = document.getElementById('messages');
    const otpModal = document.getElementById('otp-modal');
    const otpInput = document.getElementById('otp-input');
    const otpMessage = document.getElementById('otp-message');
    const otpStatus = document.getElementById('otp-status');
    const submitOtp = document.getElementById('submit-otp');
    const cancelOtp = document.getElementById('cancel-otp');
    const closeModal = document.getElementById('close-modal');
    const resetBtn = document.getElementById('reset-btn');
    const exampleItems = document.querySelectorAll('.example-item');

    // Session management
    let sessionId = localStorage.getItem('session_id') || '';
    
    // Chat functions
    function appendMessage(message, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const icon = document.createElement('i');
        icon.className = isUser ? 'fas fa-user' : 'fas fa-robot';
        avatarDiv.appendChild(icon);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const paragraph = document.createElement('p');
        paragraph.textContent = message;
        contentDiv.appendChild(paragraph);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        messagesContainer.appendChild(messageDiv);
        scrollToBottom();
    }
    
    function appendTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator bot-message';
        indicator.id = 'typing-indicator';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        const icon = document.createElement('i');
        icon.className = 'fas fa-robot';
        avatarDiv.appendChild(icon);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('span');
            contentDiv.appendChild(dot);
        }
        
        indicator.appendChild(avatarDiv);
        indicator.appendChild(contentDiv);
        
        messagesContainer.appendChild(indicator);
        scrollToBottom();
    }
    
    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
    
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    function sendMessage(message) {
        if (!message.trim()) return;
        
        appendMessage(message, true);
        userInput.value = '';
        appendTypingIndicator();
        
        fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                session_id: sessionId
            })
        })
        .then(response => response.json())
        .then(data => {
            removeTypingIndicator();
            
            if (data.session_id) {
                sessionId = data.session_id;
                localStorage.setItem('session_id', sessionId);
            }
            
            if (data.require_auth) {
                otpMessage.textContent = data.message;
                showOtpModal();
                // appendMessage(data.message, false);
            } else {
                appendMessage(data.message, false);
            }
        })
        .catch(error => {
            removeTypingIndicator();
            appendMessage('Sorry, there was an error connecting to the server. Please try again later.', false);
            console.error('Error:', error);
        });
    }
    
    function showOtpModal() {
        otpModal.classList.add('active');
        otpInput.focus();
        otpStatus.textContent = '';
    }
    
    function hideOtpModal() {
        otpModal.classList.remove('active');
        otpInput.value = '';
        otpStatus.textContent = '';
    }
    
    function submitOtpCode() {
        const otp = otpInput.value.trim();
        
        if (!otp || otp.length !== 6) {
            otpStatus.textContent = '❌ Please enter a valid 6-digit OTP';
            return;
        }
        
        fetch('/api/verify-otp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                otp: otp,
                session_id: sessionId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                hideOtpModal();
                if (data.message) {
                    appendMessage(data.message, false);
                }
            } else {
                otpStatus.textContent = data.message;
            }
        })
        .catch(error => {
            otpStatus.textContent = '❌ An error occurred. Please try again.';
            console.error('Error:', error);
        });
    }
    
    function resetConversation() {
        if (confirm('Are you sure you want to reset the conversation?')) {
            sendMessage('reset_all');
            messagesContainer.innerHTML = '';
            appendMessage('👋 Hello! I\'m your HR assistant. I can help you with leave balances, company policies, or submitting leave requests. How can I assist you today?', false);
        }
    }
    
    // Event listeners
    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const message = userInput.value;
        sendMessage(message);
    });
    
    submitOtp.addEventListener('click', submitOtpCode);
    
    otpInput.addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            submitOtpCode();
        }
    });
    
    cancelOtp.addEventListener('click', hideOtpModal);
    closeModal.addEventListener('click', hideOtpModal);
    
    resetBtn.addEventListener('click', resetConversation);
    
    exampleItems.forEach(item => {
        item.addEventListener('click', function() {
            const message = this.getAttribute('data-message');
            if (message) {
                userInput.value = message;
                userInput.focus();
            }
        });
    });
});