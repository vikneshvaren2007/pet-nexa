// ==========================================================
// PET NEXA — PETCARE AI FLOATING ASSISTANT
// ==========================================================

const FLOATING_AI_STORAGE_KEY = "petnexa_floating_ai_messages_v1";

function getStoredFloatingMessages() {
    try {
        const raw = localStorage.getItem(FLOATING_AI_STORAGE_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

function saveStoredFloatingMessages(msgs) {
    try {
        localStorage.setItem(FLOATING_AI_STORAGE_KEY, JSON.stringify(msgs));
    } catch (e) {}
}

function restoreFloatingAIMessages() {
    const messages = document.getElementById("petcareAIMessages");
    if (!messages) return;

    const list = getStoredFloatingMessages();
    if (!list || list.length === 0) return;

    messages.innerHTML = "";
    list.forEach(item => {
        const div = document.createElement("div");
        div.className = `petcare-ai-message ${item.sender}`;
        if (item.sender === "user") {
            div.textContent = item.text;
        } else {
            div.innerHTML = formatFloatingAIMarkdown(item.text);
            if (item.hasBooking) {
                const btnWrap = document.createElement("div");
                btnWrap.style.marginTop = "8px";
                btnWrap.innerHTML = `
                    <a href="booking.html" class="petcare-ai-book-btn" style="background:#8b5cf6; color:#fff; padding:6px 14px; border-radius:50px; font-size:12px; text-decoration:none; display:inline-block; font-weight:700;">
                        📅 Book Grooming Now
                    </a>
                `;
                div.appendChild(btnWrap);
            }
        }
        messages.appendChild(div);
    });

    messages.scrollTop = messages.scrollHeight;
}

function clearFloatingAIChat() {
    try {
        localStorage.removeItem(FLOATING_AI_STORAGE_KEY);
    } catch (e) {}

    const messages = document.getElementById("petcareAIMessages");
    if (messages) {
        messages.innerHTML = `
            <div class="petcare-ai-message bot">
                🐾 Hi! I am your <strong>PetCare AI Assistant</strong>. Ask me anything about grooming, pet care, or appointments!
            </div>
        `;
    }
}

function togglePetCareAI() {
    const chat = document.getElementById("petcareAIChat");
    if (!chat) {
        console.error("PetCare AI chat box not found!");
        return;
    }
    const isFlex = chat.style.display === "flex";
    chat.style.display = isFlex ? "none" : "flex";
    if (!isFlex) {
        restoreFloatingAIMessages();
    }
}

function formatFloatingAIMarkdown(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/g, "<em>$1</em>")
        .replace(/•\s*(.*?)(?=\n|$|<br>)/g, "<div style='margin-left:8px; margin-bottom:4px;'>• $1</div>")
        .replace(/\n/g, "<br>");
}

async function sendPetCareAI() {
    const input = document.getElementById("petcareAIInput");
    const messages = document.getElementById("petcareAIMessages");

    if (!input || !messages) return;

    const message = input.value.trim();
    if (!message) return;

    // Show User Message
    const userMessage = document.createElement("div");
    userMessage.className = "petcare-ai-message user";
    userMessage.textContent = message;
    messages.appendChild(userMessage);

    // Save to storage
    const stored = getStoredFloatingMessages();
    stored.push({ sender: "user", text: message, timestamp: Date.now() });
    if (stored.length > 30) stored.splice(0, stored.length - 30);
    saveStoredFloatingMessages(stored);

    input.value = "";
    messages.scrollTop = messages.scrollHeight;

    // Show Thinking Bubble
    const botMessage = document.createElement("div");
    botMessage.className = "petcare-ai-message bot";
    botMessage.innerHTML = "🐾 <em>PetCare AI is thinking...</em>";
    messages.appendChild(botMessage);
    messages.scrollTop = messages.scrollHeight;

    const API_BASE = (() => {
        const host = window.location.hostname || "127.0.0.1";
        const port = window.location.port;
        const isLocalDevServer = (host === "localhost" || host === "127.0.0.1" || host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) && port && port !== "5000" && port !== "80" && port !== "443" && port !== "";
        if (isLocalDevServer) {
            return window.location.protocol + "//" + host + ":5000";
        }
        return "";
    })();

    try {
        const response = await fetch(API_BASE + "/ai-chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message })
        });

        if (!response.ok) throw new Error("Server error: " + response.status);

        const data = await response.json();
        const replyText = data.reply || "🐾 Sorry, PetCare AI could not answer that.";
        botMessage.innerHTML = formatFloatingAIMarkdown(replyText);

        // If booking mentioned, show Book Now button
        const lowerMessage = (message + " " + replyText).toLowerCase();
        let hasBooking = false;
        if (lowerMessage.includes("book") || lowerMessage.includes("grooming") || lowerMessage.includes("appointment")) {
            hasBooking = true;
            const btnWrap = document.createElement("div");
            btnWrap.style.marginTop = "8px";
            btnWrap.innerHTML = `
                <a href="booking.html" class="petcare-ai-book-btn" style="background:#8b5cf6; color:#fff; padding:6px 14px; border-radius:50px; font-size:12px; text-decoration:none; display:inline-block; font-weight:700;">
                    📅 Book Grooming Now
                </a>
            `;
            botMessage.appendChild(btnWrap);
        }

        const updatedStored = getStoredFloatingMessages();
        updatedStored.push({ sender: "bot", text: replyText, hasBooking: hasBooking, timestamp: Date.now() });
        if (updatedStored.length > 30) updatedStored.splice(0, updatedStored.length - 30);
        saveStoredFloatingMessages(updatedStored);

    } catch (error) {
        console.error("PetCare AI Error:", error);
        botMessage.innerHTML = "🐾 Unable to connect to backend server. Please make sure Flask is running on port 5000.";
    }

    messages.scrollTop = messages.scrollHeight;
}

// Voice input for floating assistant
let floatingRecognition = null;
function startFloatingVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Voice recognition is available in Google Chrome / Edge.");
        return;
    }

    const input = document.getElementById("petcareAIInput");
    if (!input) return;

    if (floatingRecognition) {
        floatingRecognition.stop();
        floatingRecognition = null;
        return;
    }

    floatingRecognition = new SpeechRecognition();
    floatingRecognition.lang = "en-IN";
    floatingRecognition.start();

    input.placeholder = "Listening...";
    floatingRecognition.onresult = function(event) {
        input.value = event.results[0][0].transcript;
        floatingRecognition = null;
        input.placeholder = "Ask PetCare AI...";
    };
    floatingRecognition.onerror = function() {
        floatingRecognition = null;
        input.placeholder = "Ask PetCare AI...";
    };
    floatingRecognition.onend = function() {
        floatingRecognition = null;
        input.placeholder = "Ask PetCare AI...";
    };
}

document.addEventListener("DOMContentLoaded", function () {
    restoreFloatingAIMessages();
});