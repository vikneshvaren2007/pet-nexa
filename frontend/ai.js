/* ==========================================================
   PET NEXA — AI PET ADVISOR (GOOGLE GEMINI DEVELOPER API)
   Dog & Cat Specialization + Persistent Storage + Voice Input
========================================================== */

const API_BASE = (() => {
    const host = window.location.hostname || "127.0.0.1";
    const port = window.location.port;
    const isLocalDevServer = (host === "localhost" || host === "127.0.0.1" || host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) && port && port !== "5000" && port !== "80" && port !== "443" && port !== "";
    if (isLocalDevServer) {
        return window.location.protocol + "//" + host + ":5000";
    }
    return "";
})();

// LocalStorage Keys for persistent chat memory
const STORAGE_KEYS = {
    MESSAGES: "petnexa_ai_chat_messages_v1",
    HISTORY: "petnexa_ai_chat_history_v1",
    PET_TYPE: "petnexa_ai_pet_type_v1"
};

let currentPetType = "dog";
let chatHistory = [];
let isSending = false;

/* ==========================================================
   PERSISTENCE STORAGE HELPERS
========================================================== */
function getStoredMessages() {
    try {
        const raw = localStorage.getItem(STORAGE_KEYS.MESSAGES);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        console.warn("Could not read stored messages:", e);
        return [];
    }
}

function saveStoredMessages(messages) {
    try {
        localStorage.setItem(STORAGE_KEYS.MESSAGES, JSON.stringify(messages));
    } catch (e) {
        console.warn("Could not save messages to storage:", e);
    }
}

function loadStoredChatHistory() {
    try {
        const raw = localStorage.getItem(STORAGE_KEYS.HISTORY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        console.warn("Could not read stored chat history:", e);
        return [];
    }
}

function saveStoredChatHistory(history) {
    try {
        localStorage.setItem(STORAGE_KEYS.HISTORY, JSON.stringify(history));
    } catch (e) {
        console.warn("Could not save chat history to storage:", e);
    }
}

/* ==========================================================
   QUICK SUGGESTIONS DATA
========================================================== */
const SUGGESTIONS = {
    dog: [
        { label: "What food is good for my dog?", icon: "🍖", query: "What food is good for my dog?" },
        { label: "How do I know if my dog is happy?", icon: "❤️", query: "How do I know if my dog is happy?" },
        { label: "Why is my dog not eating?", icon: "❓", query: "Why is my dog not eating?" },
        { label: "Why is my dog sleeping so much?", icon: "😴", query: "Why is my dog sleeping so much?" },
        { label: "How much exercise does my dog need?", icon: "🏃", query: "How much exercise does my dog need?" },
        { label: "How should I groom my dog?", icon: "🛁", query: "How should I groom my dog?" }
    ],
    cat: [
        { label: "What food is good for my cat?", icon: "🐟", query: "What food is good for my cat?" },
        { label: "How do I know if my cat is happy?", icon: "😻", query: "How do I know if my cat is happy?" },
        { label: "Why is my cat hiding?", icon: "📦", query: "Why is my cat hiding?" },
        { label: "Why is my cat meowing so much?", icon: "🗣️", query: "Why is my cat meowing so much?" },
        { label: "What nutrients does my cat need?", icon: "🥩", query: "What nutrients does my cat need?" },
        { label: "How should I groom my cat?", icon: "🛁", query: "How should I groom my cat?" }
    ]
};

/* ==========================================================
   SET PET TYPE (DOG / CAT)
========================================================== */
function setPetType(type, saveToStorage = true) {
    if (type !== "dog" && type !== "cat") return;
    currentPetType = type;

    if (saveToStorage) {
        try {
            localStorage.setItem(STORAGE_KEYS.PET_TYPE, type);
        } catch (e) {}
    }

    // Toggle button active states
    const btnDog = document.getElementById("btnDog");
    const btnCat = document.getElementById("btnCat");
    if (btnDog && btnCat) {
        if (type === "dog") {
            btnDog.classList.add("active");
            btnCat.classList.remove("active");
        } else {
            btnCat.classList.add("active");
            btnDog.classList.remove("active");
        }
    }

    // Update Chat Top Info
    const miniLogo = document.getElementById("chatMiniLogo");
    const badge = document.getElementById("chatActivePetBadge");
    const input = document.getElementById("userInput");

    if (miniLogo) miniLogo.textContent = type === "dog" ? "🐶" : "🐱";
    if (badge) {
        badge.textContent = type === "dog"
            ? "Specialized in Dog Care & Wellness"
            : "Specialized in Cat Care & Wellness";
    }
    if (input) {
        input.placeholder = type === "dog"
            ? "Ask anything about caring for your dog..."
            : "Ask anything about caring for your cat...";
    }

    // Update Quick Suggestions
    renderQuickSuggestions();
}

/* ==========================================================
   RENDER QUICK SUGGESTIONS
========================================================== */
function renderQuickSuggestions() {
    const container = document.getElementById("quickQuestions");
    if (!container) return;

    const list = SUGGESTIONS[currentPetType] || SUGGESTIONS.dog;
    container.innerHTML = "";

    list.forEach(item => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.innerHTML = `${item.icon} <span>${item.label}</span>`;
        btn.onclick = () => askAI(item.query);
        container.appendChild(btn);
    });
}

/* ==========================================================
   FORMAT AI RESPONSE (MARKDOWN TO SAFE HTML)
========================================================== */
function formatAIResponse(text) {
    if (!text) return "";

    let formatted = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/g, "<em>$1</em>")
        .replace(/^###\s*(.*)$/gm, "<h4 style='color:#14b8a6; margin:10px 0 4px;'>$1</h4>")
        .replace(/^##\s*(.*)$/gm, "<h3 style='color:#14b8a6; margin:12px 0 6px;'>$1</h3>")
        .replace(/^•\s*(.*)$/gm, "<div class='ai-bullet'>• $1</div>")
        .replace(/^[*-]\s*(.*)$/gm, "<div class='ai-bullet'>• $1</div>")
        .replace(/\n\n/g, "<div class='ai-spacer'></div>")
        .replace(/\n/g, "<br>");

    return formatted;
}

/* ==========================================================
   DOM BUILDERS FOR USER & BOT MESSAGES
========================================================== */
function renderUserMessageDOM(text) {
    const messages = document.getElementById("aiMessages");
    if (!messages) return;

    const wrapper = document.createElement("div");
    wrapper.className = "chat-bubble-row user";

    const content = document.createElement("div");
    content.className = "bubble-content user-bubble";

    const label = document.createElement("strong");
    label.className = "bubble-sender user-sender";
    label.textContent = "YOU:";

    const body = document.createElement("div");
    body.className = "bubble-body";
    body.textContent = text;

    content.appendChild(label);
    content.appendChild(body);
    wrapper.appendChild(content);
    messages.appendChild(wrapper);
}

function renderBotMessageDOM(text, isError = false, petType = currentPetType) {
    const messages = document.getElementById("aiMessages");
    if (!messages) return;

    const wrapper = document.createElement("div");
    wrapper.className = `chat-bubble-row bot ${isError ? "msg-error" : ""}`;

    const avatar = document.createElement("div");
    avatar.className = "bubble-avatar";
    avatar.textContent = isError ? "⚠️" : (petType === "dog" ? "🐶" : "🐱");

    const content = document.createElement("div");
    content.className = "bubble-content bot-bubble";

    const label = document.createElement("strong");
    label.className = "bubble-sender ai-sender";
    label.innerHTML = `AI: <span class="ai-badge-pet">${(petType || "PET").toUpperCase()} ADVISOR</span>`;

    const body = document.createElement("div");
    body.className = "bubble-body";
    body.innerHTML = formatAIResponse(text);

    content.appendChild(label);
    content.appendChild(body);

    // If query mentions grooming/booking/spa, render quick booking action
    const lower = (text || "").toLowerCase();
    if (lower.includes("grooming") || lower.includes("booking") || lower.includes("appointment") || lower.includes("spa")) {
        const ctaBox = document.createElement("div");
        ctaBox.className = "ai-action-box";
        ctaBox.innerHTML = `
            <div style="margin-top:14px; padding-top:12px; border-top:1px dashed rgba(255,255,255,0.1); display:flex; gap:10px; flex-wrap:wrap;">
                <a href="booking.html" style="background:#14b8a6; color:#ffffff; padding:7px 15px; border-radius:8px; font-size:12px; text-decoration:none; font-weight:700; display:inline-flex; align-items:center; gap:6px; box-shadow:0 4px 12px rgba(20,184,166,0.3);">
                    📅 Book Grooming Session
                </a>
                <a href="shop.html" style="background:#0f172a; color:#ffffff; padding:7px 15px; border-radius:8px; font-size:12px; text-decoration:none; font-weight:700; display:inline-flex; align-items:center; gap:6px; border:1px solid rgba(255,255,255,0.15);">
                    🛍️ Shop Pet Food & Care
                </a>
            </div>
        `;
        content.appendChild(ctaBox);
    }

    wrapper.appendChild(avatar);
    wrapper.appendChild(content);
    messages.appendChild(wrapper);
}

/* ==========================================================
   RESTORE CHAT & INITIAL WELCOME
========================================================== */
function renderInitialWelcome() {
    const messages = document.getElementById("aiMessages");
    if (!messages) return;

    messages.innerHTML = `
        <div class="ai-welcome-box">
            <div class="ai-welcome-icon" id="welcomeIcon">🐶 🐱</div>
            <h3>How can I help your pet today?</h3>
            <p id="welcomeDescription">
                Ask anything about nutrition, toxic foods, grooming routines, sleep habits, puppy & kitten training, behavior, and daily pet wellness.
            </p>
        </div>

        <div class="chat-bubble-row bot">
            <div class="bubble-avatar">✦</div>
            <div class="bubble-content bot-bubble">
                <strong class="bubble-sender ai-sender">AI: <span class="ai-badge-pet">READY</span></strong>
                <div class="bubble-body">
                    Hi! I'm your <strong>AI Pet Advisor</strong>. Ask me anything about caring for your pet.
                </div>
            </div>
        </div>
    `;
}

function restoreChatMessages() {
    const messagesContainer = document.getElementById("aiMessages");
    if (!messagesContainer) return;

    const storedMsgs = getStoredMessages();
    chatHistory = loadStoredChatHistory();

    if (!storedMsgs || storedMsgs.length === 0) {
        renderInitialWelcome();
        return;
    }

    // Clear container and render stored conversation
    messagesContainer.innerHTML = "";

    storedMsgs.forEach(msg => {
        if (msg.sender === "user") {
            renderUserMessageDOM(msg.text);
        } else {
            renderBotMessageDOM(msg.text, msg.isError, msg.petType || currentPetType);
        }
    });

    // Scroll to latest message
    setTimeout(() => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }, 50);
}

/* ==========================================================
   ADD USER MESSAGE TO CHAT UI & PERSIST
========================================================== */
function addUserMessage(text) {
    const stored = getStoredMessages();

    // If starting fresh from welcome banner, clean initial welcome greeting
    if (stored.length === 0) {
        const messages = document.getElementById("aiMessages");
        if (messages) messages.innerHTML = "";
    }

    renderUserMessageDOM(text);

    stored.push({
        sender: "user",
        text: text,
        timestamp: Date.now()
    });
    if (stored.length > 60) stored.splice(0, stored.length - 60);
    saveStoredMessages(stored);

    const messages = document.getElementById("aiMessages");
    if (messages) messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
}

/* ==========================================================
   ADD BOT MESSAGE TO CHAT UI & PERSIST
========================================================== */
function addBotMessage(text, isError = false, petType = currentPetType) {
    renderBotMessageDOM(text, isError, petType);

    const stored = getStoredMessages();
    stored.push({
        sender: "bot",
        text: text,
        isError: isError,
        petType: petType,
        timestamp: Date.now()
    });
    if (stored.length > 60) stored.splice(0, stored.length - 60);
    saveStoredMessages(stored);

    const messages = document.getElementById("aiMessages");
    if (messages) messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
}

/* ==========================================================
   QUICK QUESTION CHIP HANDLER
========================================================== */
function askAI(question) {
    if (isSending) return;
    const input = document.getElementById("userInput");
    if (!input) return;
    input.value = question;
    sendAI();
}

/* ==========================================================
   TOAST NOTIFICATION HELPER
========================================================== */
function showAIToast(msg) {
    let toast = document.getElementById("pawzoToast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "pawzoToast";
        toast.style.cssText = "position:fixed; bottom:25px; right:25px; background:#14b8a6; color:#ffffff; padding:12px 22px; border-radius:10px; font-weight:700; font-size:14px; z-index:99999; box-shadow:0 10px 30px rgba(0,0,0,0.5); display:none; transition:all 0.3s cubic-bezier(0.4, 0, 0.2, 1); border:1px solid rgba(255,255,255,0.2);";
        document.body.appendChild(toast);
    }
    toast.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${msg}`;
    toast.style.display = "block";
    toast.style.opacity = "1";
    toast.style.transform = "translateY(0)";

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
        setTimeout(() => { toast.style.display = "none"; }, 300);
    }, 2500);
}

/* ==========================================================
   CLEAR CHAT (MANUAL RESET ONLY)
========================================================== */
function clearChat() {
    try {
        localStorage.removeItem(STORAGE_KEYS.MESSAGES);
        localStorage.removeItem(STORAGE_KEYS.HISTORY);
    } catch (e) {
        console.warn("Failed to clear local storage:", e);
    }

    chatHistory = [];
    renderInitialWelcome();

    const input = document.getElementById("userInput");
    if (input) {
        input.value = "";
        input.focus();
    }

    showAIToast("Chat history cleared 🐾");
}

/* ==========================================================
   SEND MESSAGE TO FLASK BACKEND /api/pet-advisor
========================================================== */
async function sendAI() {
    if (isSending) return;

    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("sendBtn");
    if (!input) return;

    const message = input.value.trim();
    if (!message) {
        input.focus();
        input.style.boxShadow = "0 0 0 2px #ef4444";
        setTimeout(() => { input.style.boxShadow = ""; }, 1500);
        return;
    }

    // Display user message in UI and persist to localStorage
    addUserMessage(message);
    input.value = "";

    // Set sending state & disable controls
    isSending = true;
    if (sendBtn) sendBtn.disabled = true;
    if (input) input.disabled = true;

    // Show "🐾 Thinking..." bubble
    const messages = document.getElementById("aiMessages");
    const thinking = document.createElement("div");
    thinking.className = "chat-bubble-row bot";
    thinking.id = "aiThinkingBubble";
    thinking.innerHTML = `
        <div class="bubble-avatar">🐾</div>
        <div class="bubble-content bot-bubble thinking-bubble">
            <strong class="bubble-sender ai-sender">AI:</strong>
            <div class="bubble-body thinking-text">
                <span class="thinking-spinner">🐾</span> Thinking...
            </div>
        </div>
    `;
    if (messages) {
        messages.appendChild(thinking);
        messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
    }

    try {
        const response = await fetch(API_BASE + "/api/pet-advisor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                pet_type: currentPetType,
                message: message,
                history: chatHistory.slice(-8)
            })
        });

        // Remove thinking bubble
        const thinkingMsg = document.getElementById("aiThinkingBubble");
        if (thinkingMsg) thinkingMsg.remove();

        const data = await response.json().catch(() => ({}));

        if (response.ok && data.success && data.answer) {
            addBotMessage(data.answer, false, currentPetType);
            // Save to conversational memory and persist to localStorage
            chatHistory.push({ role: "user", text: message });
            chatHistory.push({ role: "model", text: data.answer });
            if (chatHistory.length > 10) chatHistory = chatHistory.slice(-10);
            saveStoredChatHistory(chatHistory);
        } else {
            const errorText = data.error || data.answer || "AI Pet Advisor is temporarily unavailable. Please try again.";
            addBotMessage(errorText, true, currentPetType);
        }

    } catch (error) {
        console.error("AI PET ADVISOR FETCH ERROR:", error);
        const thinkingMsg = document.getElementById("aiThinkingBubble");
        if (thinkingMsg) thinkingMsg.remove();

        addBotMessage("AI Pet Advisor is temporarily unavailable. Please try again.", true, currentPetType);
    } finally {
        isSending = false;
        if (sendBtn) sendBtn.disabled = false;
        if (input) {
            input.disabled = false;
            input.focus();
        }
    }
}

/* ==========================================================
   VOICE TO TEXT (SPEECH RECOGNITION)
========================================================== */
let recognition = null;
let isListening = false;

function startVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        alert("Voice recognition is available in Google Chrome and Microsoft Edge. Please use a supported browser.");
        return;
    }

    const input = document.getElementById("userInput");
    const mic = document.getElementById("micButton");
    if (!input || !mic) return;

    if (isListening && recognition) {
        recognition.stop();
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = function () {
        isListening = true;
        mic.classList.add("recording");
        mic.textContent = "🔴";
        input.placeholder = "Listening... Speak your question now...";
    };

    recognition.onresult = function (event) {
        const transcript = event.results[0][0].transcript;
        input.value = transcript.trim();
    };

    recognition.onerror = function (event) {
        console.warn("Speech recognition error:", event.error);
        resetMic();
    };

    recognition.onend = function () {
        resetMic();
    };

    function resetMic() {
        isListening = false;
        if (mic) {
            mic.classList.remove("recording");
            mic.textContent = "🎤";
        }
        if (input) {
            input.placeholder = currentPetType === "dog"
                ? "Ask anything about caring for your dog..."
                : "Ask anything about caring for your cat...";
        }
    }

    recognition.start();
}

/* ==========================================================
   INITIALIZATION & EVENT LISTENERS
========================================================== */
document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("userInput");
    if (input) {
        input.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendAI();
            }
        });
    }

    // Check URL parameters for pet type override (e.g., ai.html?pet=cat)
    const urlParams = new URLSearchParams(window.location.search);
    const petParam = urlParams.get("pet");
    const queryParam = urlParams.get("q") || urlParams.get("query");

    // Restore saved pet type preference or use URL parameter
    let targetPetType = "dog";
    if (petParam === "dog" || petParam === "cat") {
        targetPetType = petParam;
    } else {
        try {
            const saved = localStorage.getItem(STORAGE_KEYS.PET_TYPE);
            if (saved === "dog" || saved === "cat") targetPetType = saved;
        } catch (e) {}
    }
    setPetType(targetPetType, true);

    // Restore chat history from localStorage across page visits
    restoreChatMessages();

    // If a query was passed in URL (from index.html chips), automatically ask
    if (queryParam && queryParam.trim()) {
        setTimeout(() => {
            askAI(queryParam.trim());
            // Clean URL query params without reloading
            try {
                window.history.replaceState({}, document.title, window.location.pathname);
            } catch (e) {}
        }, 150);
    }
});