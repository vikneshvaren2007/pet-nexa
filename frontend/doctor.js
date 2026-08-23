const API_BASE = (() => {
    const host = window.location.hostname || "127.0.0.1";
    const port = window.location.port;
    const isLocalDevServer = (host === "localhost" || host === "127.0.0.1" || host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) && port && port !== "5000" && port !== "80" && port !== "443" && port !== "";
    if (isLocalDevServer) {
        return window.location.protocol + "//" + host + ":5000";
    }
    return "";
})();

document.addEventListener("DOMContentLoaded", async function() {
    const urlParams = new URLSearchParams(window.location.search);
    const paramId = urlParams.get("id");
    const selectedDoctorId = paramId || localStorage.getItem("selectedDoctorId") || localStorage.getItem("selectedDoctor") || "1";
    
    try {
        const res = await fetch(API_BASE + "/api/specialists");
        if (!res.ok) return;
        const specialists = await res.json();
        
        let doctor = null;
        if (typeof selectedDoctorId === "number" || !isNaN(selectedDoctorId)) {
            doctor = specialists.find(s => s.id === parseInt(selectedDoctorId));
        }
        if (!doctor && typeof selectedDoctorId === "string") {
            const num = selectedDoctorId.replace("doctor", "");
            if (!isNaN(num)) {
                doctor = specialists[parseInt(num) - 1];
            }
        }
        if (!doctor && specialists.length > 0) {
            doctor = specialists[0];
        }

        if (doctor) {
            const imgEl = document.getElementById("doctorImage");
            if (imgEl) imgEl.src = doctor.image || "images/doctor1.jpg";
            
            const nameEl = document.getElementById("doctorName");
            if (nameEl) nameEl.textContent = doctor.name;
            
            const specEl = document.getElementById("doctorSpecialist");
            if (specEl) specEl.textContent = doctor.role || "Pet Care Specialist";
            
            const expEl = document.getElementById("doctorExperience");
            if (expEl) expEl.textContent = doctor.experience || "5+ Years";
            
            const skillsEl = document.getElementById("doctorSkills");
            if (skillsEl) skillsEl.textContent = doctor.skills || "Dog & Cat Grooming & Health";
            
            const aboutEl = document.getElementById("doctorAbout");
            if (aboutEl) aboutEl.textContent = doctor.about || "Experienced pet grooming and wellness specialist dedicated to providing gentle, anxiety-free styling and therapeutic care for pets.";

            const bookBtn = document.getElementById("bookDoctorBtn") || document.querySelector(".btn-book-doctor") || document.querySelector(".book-btn");
            if (bookBtn) {
                bookBtn.onclick = function() {
                    localStorage.setItem("selectedSpecialist", `${doctor.name} - ${doctor.role}`);
                };
            }
        }
    } catch (e) {
        console.error("Failed to load specialist details:", e);
    }
});