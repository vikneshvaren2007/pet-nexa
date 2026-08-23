// ==========================================================
// PET NEXA — MAIN INTERACTIVE JAVASCRIPT
// Dynamic Shop, Dynamic Reviews, Swiper Carousels, Cart Sync
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

document.addEventListener("DOMContentLoaded", function() {
    updateCartCount();
    loadFeaturedProducts();
    loadCustomerReviews();
    initHeroImageSlider();
    initScrollEffects();
    initCarousels();
});

// Initialize Swiper Carousels with Auto-scroll and Pause on Hover
function initCarousels() {
    if (!window.Swiper) return;

    // 1. Services Carousel
    const serviceEl = document.querySelector(".serviceSwiper");
    if (serviceEl) {
        new Swiper(".serviceSwiper", {
            slidesPerView: 3,
            spaceBetween: 25,
            loop: true,
            speed: 800,
            autoplay: {
                delay: 3000,
                disableOnInteraction: false,
                pauseOnMouseEnter: true
            },
            navigation: {
                nextEl: ".service-next",
                prevEl: ".service-prev"
            },
            breakpoints: {
                0: { slidesPerView: 1, spaceBetween: 15 },
                640: { slidesPerView: 1.5, spaceBetween: 20 },
                768: { slidesPerView: 2, spaceBetween: 20 },
                1024: { slidesPerView: 3, spaceBetween: 25 }
            }
        });
    }

    // 2. Specialists Carousel
    const doctorEl = document.querySelector(".doctorSwiper");
    if (doctorEl) {
        new Swiper(".doctorSwiper", {
            slidesPerView: 3,
            spaceBetween: 25,
            loop: true,
            speed: 800,
            autoplay: {
                delay: 3200,
                disableOnInteraction: false,
                pauseOnMouseEnter: true
            },
            navigation: {
                nextEl: ".doctor-next",
                prevEl: ".doctor-prev"
            },
            breakpoints: {
                0: { slidesPerView: 1, spaceBetween: 15 },
                640: { slidesPerView: 1.5, spaceBetween: 20 },
                768: { slidesPerView: 2, spaceBetween: 20 },
                1024: { slidesPerView: 3, spaceBetween: 25 }
            }
        });
    }
}

// Update cart counter everywhere
function updateCartCount() {
    const cart = JSON.parse(localStorage.getItem("cart")) || JSON.parse(localStorage.getItem("pawzoCart")) || [];
    const totalCount = cart.reduce((sum, item) => sum + parseInt(item.quantity || 1), 0);
    const badges = document.querySelectorAll(".cart-count-badge, #navCartCount, #controlsCartCount");
    badges.forEach(b => {
        b.textContent = totalCount;
        if (b.classList.contains("cart-count-badge") && !b.id.includes("CartCount")) {
            b.style.display = totalCount > 0 ? "inline-flex" : "none";
        }
    });
}

// Hero Image Carousel
function initHeroImageSlider() {
    const heroImg = document.getElementById("heroImage");
    if (!heroImg) return;
    const images = ["images/image.png", "images/image2.png"];
    let idx = 0;
    setInterval(() => {
        idx = (idx + 1) % images.length;
        heroImg.src = images[idx];
    }, 4000);
}

// Mobile Menu
function openMenu() {
    const menu = document.getElementById("sideMenu");
    if (menu) menu.style.right = "0";
}
function closeMenu() {
    const menu = document.getElementById("sideMenu");
    if (menu) menu.style.right = "-300px";
}

// Select Service & Navigate to Service-Specific Booking Path (Normal Services)
function selectService(slugOrName, fullName, price, duration) {
    const rawName = fullName ? fullName.split("-")[0].trim() : (slugOrName || "Basic Grooming");
    const slug = (slugOrName && !slugOrName.includes("₹"))
        ? slugOrName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
        : rawName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

    if (slug === "separate-bath" || rawName.toLowerCase().includes("separate bath")) {
        openSeparateBathModal();
        return;
    }

    const serviceObj = {
        main_service: rawName,
        sub_service: "",
        slug: slug,
        name: rawName,
        price: price || 900,
        duration: duration || "60 mins"
    };

    localStorage.setItem("mainService", rawName);
    localStorage.removeItem("subService");
    localStorage.setItem("selectedService", rawName);
    localStorage.setItem("selectedServiceSlug", slug);
    localStorage.setItem("selectedServices", JSON.stringify([serviceObj]));

    window.location.href = "booking.html?service=" + encodeURIComponent(slug);
}

// Book Home Service Helper
function bookHomeService(slug, name, price, duration) {
    selectService(slug, name, price, duration);
}

let homeSelectedBathServices = [];

// Separate Bath Modal Controls for Homepage
function openSeparateBathModal() {
    const modal = document.getElementById("separateBathModal");
    const errorMsg = document.getElementById("homeValidationErrorMsg") || document.getElementById("validationErrorMsg");
    if (errorMsg) errorMsg.style.display = "none";
    if (modal) {
        modal.classList.add("active");
        modal.style.display = "flex";
    }
}

function closeSeparateBathModal() {
    const modal = document.getElementById("separateBathModal");
    if (modal) {
        modal.classList.remove("active");
        modal.style.display = "none";
    }
}

function toggleHomeBathService(slug, name, price, duration, event) {
    const chk = document.getElementById(`home-chk-${slug}`);
    const card = document.getElementById(`home-bath-card-${slug}`);

    if (event && event.target !== chk) {
        chk.checked = !chk.checked;
    }

    const idx = homeSelectedBathServices.findIndex(s => s.slug === slug);
    if (chk.checked) {
        if (idx === -1) {
            homeSelectedBathServices.push({
                slug: slug,
                name: name,
                price: Number(price),
                duration: duration
            });
        }
        if (card) card.classList.add("selected");
    } else {
        if (idx !== -1) {
            homeSelectedBathServices.splice(idx, 1);
        }
        if (card) card.classList.remove("selected");
    }

    const errorMsg = document.getElementById("homeValidationErrorMsg") || document.getElementById("validationErrorMsg");
    if (errorMsg && homeSelectedBathServices.length > 0) {
        errorMsg.style.display = "none";
    }

    renderHomeBathLiveSummary();
}

function renderHomeBathLiveSummary() {
    const countBadge = document.getElementById("homeBathCountBadge");
    const namesList = document.getElementById("homeBathSelectedNamesList");
    const totalPriceEl = document.getElementById("homeBathLiveTotalPrice");

    const count = homeSelectedBathServices.length;
    if (countBadge) countBadge.textContent = `${count}`;

    if (count === 0) {
        if (namesList) namesList.innerHTML = `<span style="color:#64748b;">None selected yet. Please select at least 1 service.</span>`;
        if (totalPriceEl) totalPriceEl.textContent = `₹0`;
    } else {
        const total = homeSelectedBathServices.reduce((sum, s) => sum + s.price, 0);
        const namesHtml = homeSelectedBathServices.map(s => `<span style="display:inline-block; background:rgba(139,92,246,0.15); border:1px solid rgba(139,92,246,0.3); color:#ffffff; padding:2px 8px; border-radius:12px; margin:2px 4px 2px 0; font-size:11.5px;">• ${s.name} (₹${s.price})</span>`).join(" ");
        if (namesList) namesList.innerHTML = namesHtml;
        if (totalPriceEl) totalPriceEl.textContent = `₹${total.toLocaleString()}`;
    }
}

function proceedWithHomeSeparateBath() {
    const errorMsg = document.getElementById("homeValidationErrorMsg") || document.getElementById("validationErrorMsg");
    if (homeSelectedBathServices.length === 0) {
        if (errorMsg) errorMsg.style.display = "flex";
        return;
    }

    const subNames = homeSelectedBathServices.map(s => s.name).join(", ");
    const subSlugs = homeSelectedBathServices.map(s => s.slug).join(",");
    const total = homeSelectedBathServices.reduce((sum, s) => sum + s.price, 0);

    const formattedServices = homeSelectedBathServices.map(s => ({
        main_service: "Separate Bath",
        sub_service: s.name,
        slug: `separate-bath-${s.slug}`,
        name: `Separate Bath — ${s.name}`,
        price: s.price,
        duration: s.duration
    }));

    localStorage.setItem("mainService", "Separate Bath");
    localStorage.setItem("subService", subNames);
    localStorage.setItem("selectedService", `Separate Bath — ${subNames}`);
    localStorage.setItem("selectedServiceSlug", "separate-bath");
    localStorage.setItem("selectedServices", JSON.stringify(formattedServices));

    window.location.href = `booking.html?service=separate-bath&sub=${encodeURIComponent(subSlugs)}`;
}

// Select Specialist & Navigate to Booking
function selectSpecialist(specialistName) {
    localStorage.setItem("selectedSpecialist", specialistName);
    window.location.href = "booking.html";
}

// Open Doctor Profile
function openDoctor(doctorId) {
    localStorage.setItem("selectedDoctor", doctorId);
    window.location.href = "doctor.html";
}

// Service Details Modal
function openServiceModal(title, price, duration, desc, slug) {
    const modal = document.getElementById("serviceDetailsModal");
    if (!modal) return;

    const actualSlug = slug || title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    const numPrice = parseInt(String(price).replace(/[^0-9]/g, '')) || 500;

    const titleEl = document.getElementById("modalServiceTitle");
    const priceEl = document.getElementById("modalServicePrice");
    const durationEl = document.getElementById("modalServiceDuration");
    const descEl = document.getElementById("modalServiceDesc");

    if (titleEl) titleEl.textContent = title;
    if (priceEl) priceEl.textContent = price;
    if (durationEl) durationEl.innerHTML = `<i class="fa-regular fa-clock"></i> ${duration}`;
    if (descEl) descEl.textContent = desc;

    const bookBtn = document.getElementById("modalBookBtn");
    if (bookBtn) {
        bookBtn.onclick = function(e) {
            e.preventDefault();
            closeServiceModal();
            if (actualSlug === "separate-bath") {
                openSeparateBathModal();
            } else {
                selectService(actualSlug, title, numPrice, duration);
            }
        };
    }

    modal.style.display = "flex";
}

function closeServiceModal(event) {
    if (event && event.target !== event.currentTarget && !event.target.classList.contains("modal-close") && !event.target.classList.contains("btn-view-details")) {
        return;
    }
    const modal = document.getElementById("serviceDetailsModal");
    if (modal) modal.style.display = "none";
}


// Load Featured Products from Backend Database
async function loadFeaturedProducts() {
    const container = document.getElementById("featuredProductsGrid");
    if (!container) return;

    try {
        const res = await fetch(API_BASE + "/api/products");
        if (!res.ok) throw new Error("Failed to fetch products");
        const products = await res.json();

        if (!products || products.length === 0) {
            container.innerHTML = `<p style="grid-column: 1/-1; text-align:center; color:#94a3b8;">No products currently available.</p>`;
            return;
        }

        const top4 = products.slice(0, 4);
        container.innerHTML = top4.map(p => `
            <div class="product-item-card">
                <div class="product-badge">${p.category ? p.category.toUpperCase() : 'SUPPLY'}</div>
                <img src="${p.image || 'images/logo.jpg'}" alt="${p.name}" class="product-thumb">
                <div class="product-info">
                    <h4>${p.name}</h4>
                    <p>${p.description ? p.description.substring(0, 75) : ''}...</p>
                    <div class="product-price-row">
                        <span class="price-now">₹${p.discount_price > 0 ? p.discount_price.toFixed(0) : p.price.toFixed(0)}</span>
                        ${p.discount_price > 0 ? `<span class="price-was">₹${p.price.toFixed(0)}</span>` : ''}
                    </div>
                    <button class="btn-add-quick" onclick="addToCartQuick(${p.id}, '${p.name.replace(/'/g, "\\'")}', ${p.discount_price > 0 ? p.discount_price : p.price}, '${p.image || 'images/logo.jpg'}')">
                        <i class="fa-solid fa-cart-shopping"></i> Add to Cart
                    </button>
                </div>
            </div>
        `).join("");

    } catch (e) {
        console.error("Products load error:", e);
        if (container) {
            container.innerHTML = `<p style="grid-column: 1/-1; text-align:center; color:#94a3b8;">Visit our <a href="shop.html" style="color:#14b8a6; font-weight:700;">Pet Shop</a> to explore premium supplies.</p>`;
        }
    }
}

// Add to Cart from Homepage
function addToCartQuick(id, name, price, image) {
    let cart = JSON.parse(localStorage.getItem("cart")) || JSON.parse(localStorage.getItem("pawzoCart")) || [];
    const existing = cart.find(item => item.id == id || item.name == name);

    if (existing) {
        existing.quantity = parseInt(existing.quantity) + 1;
    } else {
        cart.push({ id, name, price: parseFloat(price), quantity: 1, image });
    }

    localStorage.setItem("cart", JSON.stringify(cart));
    localStorage.setItem("pawzoCart", JSON.stringify(cart));
    updateCartCount();
    showToast(`🛒 "${name}" added to your cart!`);
}

// Load Customer Reviews from Backend Database
async function loadCustomerReviews() {
    const container = document.getElementById("reviewsWrapper");
    if (!container) return;

    try {
        const res = await fetch(API_BASE + "/api/reviews");
        if (!res.ok) throw new Error("Failed to fetch reviews");
        const reviews = await res.json();

        if (!reviews || reviews.length === 0) {
            container.innerHTML = `
                <div style="text-align:center; padding:30px; color:#94a3b8; width:100%;">
                    <p style="font-size:16px;">🐾 Be the first to share your pet's experience with PET NEXA!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = reviews.map(r => `
            <div class="swiper-slide">
                <div class="review-card">
                    <div class="review-stars">${"★".repeat(r.rating)}${"☆".repeat(5 - r.rating)}</div>
                    <p class="review-quote">"${r.review_text}"</p>
                    <div class="review-author">
                        <div class="author-avatar">${r.customer_name ? r.customer_name.substring(0, 1) : 'P'}</div>
                        <div>
                            <h5>${r.customer_name} <span class="verified-tag">✓ Verified Pet Parent</span></h5>
                            <span class="review-tag">${r.service_name ? 'Service: ' + r.service_name : (r.product_name ? 'Product: ' + r.product_name : 'General Care')}</span>
                        </div>
                    </div>
                </div>
            </div>
        `).join("");

        if (window.Swiper) {
            new Swiper(".reviewSwiper", {
                loop: reviews.length > 2,
                speed: 800,
                autoplay: {
                    delay: 3500,
                    disableOnInteraction: false,
                    pauseOnMouseEnter: true
                },
                slidesPerView: 3,
                spaceBetween: 25,
                breakpoints: {
                    0: { slidesPerView: 1, spaceBetween: 15 },
                    640: { slidesPerView: 1.5, spaceBetween: 20 },
                    768: { slidesPerView: 2, spaceBetween: 20 },
                    1024: { slidesPerView: 3, spaceBetween: 25 }
                }
            });
        }

    } catch (e) {
        console.error("Reviews load error:", e);
    }
}

// Toast Notification
function showToast(msg) {
    let toast = document.getElementById("pawzoToast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "pawzoToast";
        toast.style.cssText = "position:fixed; bottom:25px; right:25px; background:#7c3aed; color:#fff; padding:14px 24px; border-radius:10px; font-weight:700; z-index:99999; box-shadow:0 10px 25px rgba(124,58,237,0.4); display:none; transition:0.3s;";
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.display = "block";
    setTimeout(() => { toast.style.display = "none"; }, 3000);
}


// Scroll Header effect
function initScrollEffects() {
    window.addEventListener("scroll", () => {
        const header = document.querySelector("header");
        if (header) {
            if (window.scrollY > 40) {
                header.style.background = "#0f172a";
                header.style.boxShadow = "0 8px 20px rgba(0,0,0,0.4)";
            } else {
                header.style.background = "rgba(15, 23, 42, 0.95)";
                header.style.boxShadow = "none";
            }
        }
    });
}
