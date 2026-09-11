// ==========================================================
// PET NEXA — BOOKING & CUSTOMER DETAILS CONTROLLER
// Handles Standard Grooming & Special Separate Bath Flows
// ==========================================================

const API_BASE = (() => {
    const host = window.location.hostname || "127.0.0.1";
    const port = window.location.port;
    const isLocalDevServer = (host === "localhost" || host === "127.0.0.1" || host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) && port && port !== "5000" && port !== "80" && port !== "443" && port !== "";
    if (isLocalDevServer) {
        return window.location.protocol + "//" + host + ":5000";
    }
    return "";
})();

let globalServices = [];
let activeBookingSelection = {
    main_service: "",
    sub_service: "",
    slug: "",
    name: "",
    price: 0,
    duration: "45 mins"
};

// Standard Services Catalog
const STANDARD_SERVICES_MAP = {
    "puppy-grooming": { name: "Puppy Grooming", price: 800, duration: "45 mins" },
    "basic-grooming": { name: "Basic Grooming", price: 900, duration: "60 mins" },
    "premium-spa-bath": { name: "Premium Spa Bath", price: 1200, duration: "75 mins" },
    "premium-grooming": { name: "Premium Grooming", price: 1500, duration: "90 mins" },
    "medicated-bath": { name: "Medicated Skin Bath", price: 1100, duration: "60 mins" },
    "luxury-full-grooming": { name: "Luxury Full Grooming", price: 2200, duration: "120 mins" },
    "separate-bath": { name: "Separate Bath", price: 350, duration: "20-45 mins" }
};

// Separate Bath 10 Individual Services Catalog
const SEPARATE_BATH_INDIVIDUAL_MAP = {
    "ear-cleaning": { name: "Ear Cleaning", price: 350, duration: "20 mins" },
    "brushing": { name: "Brushing", price: 300, duration: "20 mins" },
    "bath": { name: "Bath", price: 500, duration: "40 mins" },
    "nail-trimming": { name: "Nail Trimming", price: 300, duration: "20 mins" },
    "hair-trimming": { name: "Hair Trimming", price: 450, duration: "30 mins" },
    "teeth-cleaning": { name: "Teeth Cleaning", price: 350, duration: "20 mins" },
    "paw-cleaning": { name: "Paw Cleaning", price: 300, duration: "20 mins" },
    "eye-cleaning": { name: "Eye Cleaning", price: 250, duration: "15 mins" },
    "de-shedding": { name: "De-shedding", price: 600, duration: "45 mins" },
    "flea-tick-care": { name: "Flea & Tick Care", price: 500, duration: "40 mins" }
};

// 1. Resolve Target Service from URL and LocalStorage
function resolveRequestedService() {
    const urlParams = new URLSearchParams(window.location.search);
    const path = window.location.pathname.toLowerCase();
    
    let serviceParam = urlParams.get("service");
    let subParam = urlParams.get("sub") || urlParams.get("sub_service");

    // Path match (e.g. /book/puppy-grooming or /book/separate-bath)
    const pathMatch = path.match(/\/(?:book|service|services)\/([a-z0-9-]+)/);
    if (!serviceParam && pathMatch && pathMatch[1] && pathMatch[1] !== "services.html" && pathMatch[1] !== "services") {
        serviceParam = pathMatch[1];
    }

    // Check localStorage fallback
    const storedMain = localStorage.getItem("mainService") || "";
    const storedSub = localStorage.getItem("subService") || "";
    const storedSlug = localStorage.getItem("selectedServiceSlug") || "";
    let storedServicesList = [];
    try {
        storedServicesList = JSON.parse(localStorage.getItem("selectedServices") || "[]");
    } catch(e) {
        storedServicesList = [];
    }

    if (!serviceParam && storedSlug) {
        serviceParam = storedSlug;
    }
    if (!subParam && storedSub) {
        subParam = storedSub;
    }

    // Default if completely empty
    if (!serviceParam) {
        serviceParam = "basic-grooming";
    }

    const cleanServiceSlug = serviceParam.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

    // Case A: Separate Bath Flow (Can have 1 to 10 sub-services)
    if (cleanServiceSlug === "separate-bath" || storedMain === "Separate Bath") {
        let chosenItems = [];

        // 1. Check storedServicesList from localStorage
        if (Array.isArray(storedServicesList) && storedServicesList.length > 0) {
            storedServicesList.forEach(item => {
                const subName = item.sub_service || item.name || "";
                const cleanName = subName.replace(/^Separate Bath\s*[—\-]\s*/, "").split("(")[0].trim();
                const subSlug = cleanName.toLowerCase().replace(/[^a-z0-9]+/g, '-');
                const matched = SEPARATE_BATH_INDIVIDUAL_MAP[subSlug] || {
                    name: cleanName || "Ear Cleaning",
                    price: Number(item.price) || 350,
                    duration: item.duration || "20 mins"
                };
                if (!chosenItems.some(ci => ci.name === matched.name)) {
                    chosenItems.push({
                        slug: subSlug,
                        name: matched.name,
                        price: matched.price,
                        duration: matched.duration
                    });
                }
            });
        }

        // 2. Check URL sub parameter (comma-separated slugs or names)
        if (chosenItems.length === 0 && subParam) {
            const rawParts = subParam.split(",");
            rawParts.forEach(p => {
                const cleanP = p.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
                const matched = SEPARATE_BATH_INDIVIDUAL_MAP[cleanP];
                if (matched && !chosenItems.some(ci => ci.name === matched.name)) {
                    chosenItems.push({
                        slug: cleanP,
                        name: matched.name,
                        price: matched.price,
                        duration: matched.duration
                    });
                } else if (!matched) {
                    for (const [k, v] of Object.entries(SEPARATE_BATH_INDIVIDUAL_MAP)) {
                        if (v.name.toLowerCase() === p.trim().toLowerCase() && !chosenItems.some(ci => ci.name === v.name)) {
                            chosenItems.push({
                                slug: k,
                                name: v.name,
                                price: v.price,
                                duration: v.duration
                            });
                            break;
                        }
                    }
                }
            });
        }

        // Fallback default
        if (chosenItems.length === 0) {
            chosenItems = [{
                slug: "ear-cleaning",
                name: "Ear Cleaning",
                price: 350,
                duration: "20 mins"
            }];
        }

        const subNamesStr = chosenItems.map(i => i.name).join(", ");
        const totalPrice = chosenItems.reduce((sum, i) => sum + i.price, 0);

        activeBookingSelection = {
            main_service: "Separate Bath",
            sub_service: subNamesStr,
            slug: "separate-bath",
            name: `Separate Bath — ${subNamesStr}`,
            price: totalPrice,
            duration: `${chosenItems.length * 20} mins`,
            items: chosenItems
        };
    } 
    // Case B: Standard Service Package Flow
    else {
        const stdMeta = STANDARD_SERVICES_MAP[cleanServiceSlug] || {
            name: cleanServiceSlug.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" "),
            price: 900,
            duration: "60 mins"
        };

        activeBookingSelection = {
            main_service: stdMeta.name,
            sub_service: "",
            slug: cleanServiceSlug,
            name: stdMeta.name,
            price: stdMeta.price,
            duration: stdMeta.duration,
            items: []
        };
    }
}

// 2. Render Booking Summary Box
function renderBookingSummary() {
    const banner = document.getElementById("selectedServiceBanner");
    const listEl = document.getElementById("bookingServicesList");
    const totalEl = document.getElementById("bookingPackageTotal");
    const nameEl = document.getElementById("bannerServiceName");
    const catTag = document.getElementById("bannerCategoryTag");

    if (!banner || !listEl || !totalEl) return;

    banner.style.display = "flex";

    if (activeBookingSelection.main_service === "Separate Bath" && activeBookingSelection.items && activeBookingSelection.items.length > 0) {
        if (catTag) catTag.textContent = "SEPARATE BATH • TARGETED CARE";
        if (nameEl) nameEl.textContent = "Separate Bath";

        const itemsHtml = activeBookingSelection.items.map(item => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.06); font-size:13px;">
                <span style="color:#ffffff; font-weight:600;"><i class="fa-solid fa-check" style="color:var(--primary); font-size:11px; margin-right:6px;"></i> ${item.name}</span>
                <span style="color:#22c55e; font-weight:700; font-size:13px;">₹${item.price}</span>
            </div>
        `).join("");

        listEl.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 0;">
                <span style="color:#94a3b8; font-size:13px; font-weight:600;">Main Service:</span>
                <span style="color:#ffffff; font-size:13.5px; font-weight:700;"><i class="fa-solid fa-bath" style="color:var(--primary); margin-right:5px;"></i> Separate Bath</span>
            </div>
            <div style="padding-top:6px; border-top:1px dashed rgba(255,255,255,0.08);">
                <div style="color:#94a3b8; font-size:12.5px; font-weight:600; margin-bottom:6px;">
                    Selected Services (${activeBookingSelection.items.length}):
                </div>
                <div style="background:rgba(0,0,0,0.25); border-radius:8px; padding:4px 10px;">
                    ${itemsHtml}
                </div>
            </div>
        `;
    } else {
        if (catTag) catTag.textContent = "SIGNATURE GROOMING PACKAGE";
        if (nameEl) nameEl.textContent = activeBookingSelection.main_service || "Selected Service";

        listEl.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 0;">
                <span style="color:#94a3b8; font-size:13px; font-weight:600;">Service Package:</span>
                <span style="color:#ffffff; font-size:14px; font-weight:800;">🐾 ${activeBookingSelection.main_service}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 0; font-size:12px; color:#64748b;">
                <span>Estimated Duration:</span>
                <span style="color:#cbd5e1; font-weight:600;"><i class="fa-regular fa-clock"></i> ${activeBookingSelection.duration}</span>
            </div>
        `;
    }

    totalEl.textContent = `₹${activeBookingSelection.price.toLocaleString()}`;

    // Update hidden form inputs
    const mainInp = document.getElementById("mainServiceInput");
    const subInp = document.getElementById("subServiceInput");
    if (mainInp) mainInp.value = activeBookingSelection.main_service;
    if (subInp) subInp.value = activeBookingSelection.sub_service;
}

// 3. Handle Manual Service Dropdown Change
function handleServiceSelectChange() {
    const select = document.getElementById("serviceSelect");
    const selectedVal = select.value;
    if (!selectedVal) return;

    if (selectedVal.startsWith("Separate Bath — ") || selectedVal.startsWith("Separate Bath - ")) {
        const subName = selectedVal.replace(/^Separate Bath\s*[—\-]\s*/, "").split("(")[0].trim();
        const subSlug = subName.toLowerCase().replace(/[^a-z0-9]+/g, '-');
        const meta = SEPARATE_BATH_INDIVIDUAL_MAP[subSlug] || { name: subName, price: 350, duration: "20 mins" };

        activeBookingSelection = {
            main_service: "Separate Bath",
            sub_service: meta.name,
            slug: `separate-bath-${subSlug}`,
            name: `Separate Bath — ${meta.name}`,
            price: meta.price,
            duration: meta.duration,
            items: [{ slug: subSlug, name: meta.name, price: meta.price, duration: meta.duration }]
        };
    } else {
        const matched = globalServices.find(s => s.name.toLowerCase() === selectedVal.toLowerCase());
        const slug = matched ? matched.slug : selectedVal.toLowerCase().replace(/[^a-z0-9]+/g, '-');
        const price = matched ? matched.price : (STANDARD_SERVICES_MAP[slug]?.price || 900);
        const duration = matched ? matched.duration : (STANDARD_SERVICES_MAP[slug]?.duration || "60 mins");

        activeBookingSelection = {
            main_service: selectedVal,
            sub_service: "",
            slug: slug,
            name: selectedVal,
            price: Number(price),
            duration: duration,
            items: []
        };
    }

    renderBookingSummary();
}

// 4. Dynamic Breed Filter (Dog / Cat)
function changeBreed() {
    const petType = document.getElementById("petType").value;
    const breed = document.getElementById("breed");
    if (!breed) return;
    breed.innerHTML = "";

    if (petType === "dog") {
        const dogBreeds = [
            "Labrador Retriever", "Golden Retriever", "German Shepherd", "Beagle",
            "Pug", "Shih Tzu", "Rottweiler", "Doberman", "Siberian Husky", "Pomeranian",
            "Cocker Spaniel", "Indie / Indian Pariah", "Other Dog Breed"
        ];
        breed.innerHTML = '<option value="">Select Dog Breed</option>';
        dogBreeds.forEach(dog => {
            breed.innerHTML += `<option value="${dog}">${dog}</option>`;
        });
    } else if (petType === "cat") {
        const catBreeds = [
            "Persian Cat", "Siamese", "Maine Coon", "British Shorthair",
            "Ragdoll", "Bengal", "Russian Blue", "Scottish Fold",
            "Indie / Domestic Cat", "Other Cat Breed"
        ];
        breed.innerHTML = '<option value="">Select Cat Breed</option>';
        catBreeds.forEach(cat => {
            breed.innerHTML += `<option value="${cat}">${cat}</option>`;
        });
    } else {
        breed.innerHTML = '<option value="">Select Pet Type First</option>';
    }
// Legacy customer purge helper
function purgeLegacyPersonalData() {
    const legacyValues = [
        "viknesh varen", "viknesh", "9445437069", "9488259088",
        "vikneshvaren2@gmail.com", "karthikthanesh92@gmail.com",
        "8/30 church street", "azhagappapuram"
    ];
    function containsLegacy(val) {
        if (!val || typeof val !== "string") return false;
        const lower = val.toLowerCase();
        return legacyValues.some(leg => lower.includes(leg));
    }

    const keysToCheck = ["customer_name", "phone", "email", "address", "city", "state", "pincode", "notes"];
    keysToCheck.forEach(k => {
        const v = localStorage.getItem(k);
        if (containsLegacy(v)) {
            localStorage.removeItem(k);
        }
    });

    const custDetailsStr = localStorage.getItem("customerDetails");
    if (custDetailsStr && containsLegacy(custDetailsStr)) {
        localStorage.removeItem("customerDetails");
    }

    const savedDetailsStr = localStorage.getItem("petnexa_saved_customer");
    if (savedDetailsStr && containsLegacy(savedDetailsStr)) {
        localStorage.removeItem("petnexa_saved_customer");
        localStorage.removeItem("petnexa_remember_customer");
    }
}

function clearSavedBookingCustomerDetails() {
    localStorage.removeItem("petnexa_saved_customer");
    localStorage.removeItem("petnexa_remember_customer");
    localStorage.removeItem("customerDetails");
    localStorage.removeItem("customer_name");
    localStorage.removeItem("phone");
    localStorage.removeItem("email");
    localStorage.removeItem("address");

    if (document.getElementById("custNameInput")) document.getElementById("custNameInput").value = "";
    if (document.getElementById("custPhoneInput")) document.getElementById("custPhoneInput").value = "";
    if (document.getElementById("custEmailInput")) document.getElementById("custEmailInput").value = "";
    if (document.getElementById("custAddressInput")) document.getElementById("custAddressInput").value = "";

    const rememberCheckbox = document.getElementById("bookingRememberDetails");
    if (rememberCheckbox) rememberCheckbox.checked = false;

    const clearBox = document.getElementById("bookingClearSavedBox");
    if (clearBox) clearBox.style.display = "none";

    alert("Saved customer details cleared from this browser.");
}

// 5. On DOM Ready: Populate Fields, Load API Data
document.addEventListener("DOMContentLoaded", async function() {
    // Purge legacy contaminated data
    purgeLegacyPersonalData();

    // Set minimum date to today
    const dateInput = document.getElementById("appointmentDateInput");
    if (dateInput) {
        const today = new Date().toISOString().split('T')[0];
        dateInput.min = today;
        dateInput.value = today;
    }

    // Prefill customer details ONLY if user explicitly opted in on this device
    const isRemembered = localStorage.getItem("petnexa_remember_customer") === "true";
    const rememberCheckbox = document.getElementById("bookingRememberDetails");
    const clearBox = document.getElementById("bookingClearSavedBox");

    if (isRemembered) {
        if (rememberCheckbox) rememberCheckbox.checked = true;
        if (clearBox) clearBox.style.display = "flex";

        let saved = {};
        try {
            saved = JSON.parse(localStorage.getItem("petnexa_saved_customer") || "{}");
        } catch(e) {
            saved = {};
        }

        if (document.getElementById("custNameInput")) {
            document.getElementById("custNameInput").value = saved.name || localStorage.getItem("customer_name") || "";
        }
        if (document.getElementById("custPhoneInput")) {
            document.getElementById("custPhoneInput").value = saved.phone || localStorage.getItem("phone") || "";
        }
        if (document.getElementById("custEmailInput")) {
            document.getElementById("custEmailInput").value = saved.email || localStorage.getItem("email") || "";
        }
        if (document.getElementById("custAddressInput")) {
            document.getElementById("custAddressInput").value = saved.address || localStorage.getItem("address") || "";
        }
    } else {
        // New customer: completely empty
        if (rememberCheckbox) rememberCheckbox.checked = false;
        if (clearBox) clearBox.style.display = "none";

        if (document.getElementById("custNameInput")) document.getElementById("custNameInput").value = "";
        if (document.getElementById("custPhoneInput")) document.getElementById("custPhoneInput").value = "";
        if (document.getElementById("custEmailInput")) document.getElementById("custEmailInput").value = "";
        if (document.getElementById("custAddressInput")) document.getElementById("custAddressInput").value = "";
    }

    // 1. Resolve requested service from URL or session
    resolveRequestedService();
    renderBookingSummary();

    // 2. Load Services from API
    try {
        const res = await fetch(API_BASE + "/api/services");
        if (res.ok) {
            globalServices = await res.json();
            const serviceSelect = document.getElementById("serviceSelect");
            if (serviceSelect) {
                let html = '<option value="">Select Grooming Service</option>';

                // If Separate Bath is currently active, prepend it
                if (activeBookingSelection.main_service === "Separate Bath" && activeBookingSelection.sub_service) {
                    html += `<option value="Separate Bath — ${activeBookingSelection.sub_service}" selected>🛁 Separate Bath — ${activeBookingSelection.sub_service} (₹${activeBookingSelection.price})</option>`;
                }

                // Add 10 Separate Bath options
                html += `<optgroup label="✨ Separate Bath (Individual Treatments)">`;
                for (const [sSlug, sData] of Object.entries(SEPARATE_BATH_INDIVIDUAL_MAP)) {
                    const isSel = activeBookingSelection.main_service === "Separate Bath" && activeBookingSelection.sub_service === sData.name;
                    html += `<option value="Separate Bath — ${sData.name}" ${isSel ? 'selected' : ''}>• ${sData.name} (₹${sData.price} • ${sData.duration})</option>`;
                }
                html += `</optgroup>`;

                // Add Signature Packages
                html += `<optgroup label="👑 Signature Grooming Packages">`;
                globalServices.forEach(s => {
                    if (s.slug !== "separate-bath") {
                        const isSelected = activeBookingSelection.main_service === s.name;
                        html += `<option value="${s.name}" ${isSelected ? "selected" : ""}>${s.name} (₹${Math.round(s.price)} • ${s.duration || '60 mins'})</option>`;
                    }
                });
                html += `</optgroup>`;

                serviceSelect.innerHTML = html;
            }
        }
    } catch (e) {
        console.error("Failed to load services:", e);
    }

    // 3. Load Specialists from API
    try {
        const res = await fetch(API_BASE + "/api/specialists");
        if (res.ok) {
            const specialists = await res.json();
            const specSelect = document.getElementById("specialistSelect");
            if (specSelect) {
                let html = '<option value="">Select Stylist / Specialist</option>';
                const preselectedSpec = localStorage.getItem("selectedSpecialist") || "";

                specialists.forEach(spec => {
                    const fullName = `${spec.name} - ${spec.role}`;
                    const isSelected = (preselectedSpec && preselectedSpec.toLowerCase().includes(spec.name.toLowerCase())) ? "selected" : "";
                    html += `<option value="${fullName}" ${isSelected}>${spec.name} (${spec.experience || 'Specialist'} • ${spec.skills})</option>`;
                });
                specSelect.innerHTML = html;
            }
        }
    } catch (e) {
        console.error("Failed to load specialists:", e);
    }
});

// 6. Form Submission Handler with Validation
document.getElementById("bookingForm").addEventListener("submit", async function(e) {
    e.preventDefault();
    const form = this;
    const button = form.querySelector(".confirm-btn");

    // Clear previous error styles
    document.querySelectorAll(".field-error").forEach(el => {
        el.style.display = "none";
        el.textContent = "";
    });

    const custName = form.elements["Customer_Name"].value.trim();
    const phone = form.elements["Phone_Number"].value.trim();
    const email = form.elements["Email"].value.trim();
    const petName = form.elements["Pet_Name"].value.trim();
    const petAge = form.elements["Pet_Age"].value.trim();
    const petType = form.elements["Pet_Type"].value;
    const breed = form.elements["Breed"].value;
    const specialist = form.elements["Specialist"].value;
    const appointmentDate = form.elements["Appointment_Date"].value;
    const appointmentTime = form.elements["Appointment_Time"].value;
    const address = (form.elements["Address"] ? form.elements["Address"].value.trim() : "");
    const message = (form.elements["Message"] ? form.elements["Message"].value.trim() : "");

    // Validation
    let hasError = false;

    if (!custName) {
        showError("nameError", "Please enter your full name.");
        hasError = true;
    }

    if (!phone || !/^[6-9]\d{9}$/.test(phone)) {
        showError("phoneError", "Please enter a valid 10-digit Indian mobile number.");
        hasError = true;
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        showError("emailError", "Please enter a valid email address.");
        hasError = true;
    }

    if (!petName) {
        showError("petNameError", "Please enter your pet's name.");
        hasError = true;
    }

    if (!petType) {
        showError("petTypeError", "Please select your pet type (Dog or Cat).");
        hasError = true;
    }

    if (!specialist) {
        showError("specialistError", "Please select a Pet Stylist.");
        hasError = true;
    }

    if (!appointmentDate) {
        showError("dateError", "Please select an appointment date.");
        hasError = true;
    }

    if (hasError) return;

    button.disabled = true;
    button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Confirming Appointment...`;

    // Format service string
    let serviceString = activeBookingSelection.name;
    if (activeBookingSelection.main_service === "Separate Bath" && activeBookingSelection.sub_service) {
        serviceString = `Separate Bath — ${activeBookingSelection.sub_service} (₹${activeBookingSelection.price})`;
    }

    const servicesPayload = (activeBookingSelection.items && activeBookingSelection.items.length > 0)
        ? activeBookingSelection.items.map(it => ({
            name: `Separate Bath — ${it.name}`,
            main_service: "Separate Bath",
            sub_service: it.name,
            price: it.price,
            duration: it.duration
        }))
        : [{
            name: activeBookingSelection.name,
            main_service: activeBookingSelection.main_service,
            sub_service: activeBookingSelection.sub_service || "",
            price: activeBookingSelection.price,
            duration: activeBookingSelection.duration
        }];

    const payload = {
        Customer_Name: custName,
        Phone_Number: phone,
        Email: email,
        Pet_Name: petName,
        Pet_Age: petAge,
        Pet_Type: petType,
        Breed: breed || "Standard Breed",
        Main_Service: activeBookingSelection.main_service,
        Sub_Service: activeBookingSelection.sub_service,
        Service: serviceString,
        services: servicesPayload,
        Specialist: specialist,
        Appointment_Date: appointmentDate,
        Appointment_Time: appointmentTime,
        Address: address,
        Message: message
    };

    // Store customer details in localStorage ONLY if customer opted in
    const shouldRemember = document.getElementById("bookingRememberDetails") ? document.getElementById("bookingRememberDetails").checked : false;
    if (shouldRemember) {
        const custObj = {
            name: custName,
            phone: phone,
            email: email,
            address: address
        };
        localStorage.setItem("petnexa_remember_customer", "true");
        localStorage.setItem("petnexa_saved_customer", JSON.stringify(custObj));
        localStorage.setItem("customer_name", custName);
        localStorage.setItem("phone", phone);
        localStorage.setItem("email", email);
        if (address) localStorage.setItem("address", address);
    } else {
        localStorage.removeItem("petnexa_remember_customer");
        localStorage.removeItem("petnexa_saved_customer");
    }

    try {
        const response = await fetch(API_BASE + "/api/bookings/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Booking failed.");
        }

        // Clean up temporary service selections
        localStorage.removeItem("selectedServices");
        localStorage.removeItem("selectedService");
        localStorage.removeItem("selectedServiceSlug");
        localStorage.removeItem("mainService");
        localStorage.removeItem("subService");

        localStorage.setItem("lastBooking", JSON.stringify(result.booking));
        localStorage.setItem("lastBookingId", result.booking_id);

        window.location.href = "success.html?id=" + result.booking_id;
    } catch (error) {
        console.error("Booking Error:", error);
        alert("Booking could not be completed: " + error.message);
        button.disabled = false;
        button.innerHTML = `<i class="fa-solid fa-calendar-check"></i> Confirm Appointment`;
    }
});

function showError(elId, msg) {
    const el = document.getElementById(elId);
    if (el) {
        el.textContent = msg;
        el.style.display = "block";
    }
}