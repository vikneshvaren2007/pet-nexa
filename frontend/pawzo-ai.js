// ==========================================================
// PET NEXA — PETCARE AI FLOATING ASSISTANT
// ==========================================================

function togglePetCareAI() {
    const chat = document.getElementById("petcareAIChat");
    if (!chat) {
        console.error("PetCare AI chat box not found!");
        return;
    }
    chat.style.display = (chat.style.display === "flex") ? "none" : "flex";
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
        botMessage.innerHTML = formatFloatingAIMarkdown(data.reply || "🐾 Sorry, PetCare AI could not answer that.");

        // If booking mentioned, show Book Now button
        const lowerMessage = message.toLowerCase();
        if (lowerMessage.includes("book") || lowerMessage.includes("grooming") || lowerMessage.includes("appointment")) {
            const btnWrap = document.createElement("div");
            btnWrap.style.marginTop = "8px";
            btnWrap.innerHTML = `
                <a href="booking.html" class="petcare-ai-book-btn" style="background:#8b5cf6; color:#fff; padding:6px 14px; border-radius:50px; font-size:12px; text-decoration:none; display:inline-block; font-weight:700;">
                    📅 Book Grooming Now
                </a>
            `;
            botMessage.appendChild(btnWrap);
        }

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