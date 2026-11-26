/**
 * Codozent CMS Universal Real-Time Hydration Engine
 * Automatically hydrates static HTML pages on Cloudflare Pages (codozent.com)
 * with the latest live data from Render + Supabase backend.
 * Zero build delay: Updates reflect immediately on page load!
 */
(function() {
    'use strict';

    // Cloudflare Worker handles API endpoints directly on same origin (codozent.com)
    const API_BASE = '';

    function cleanUrl(url) {
        if (!url) return '';
        const trimmed = url.trim();
        if (trimmed.startsWith('res.cloudinary.com')) {
            return `https://${trimmed}`;
        }
        return trimmed;
    }

    async function fetchJson(endpoint) {
        try {
            // Append timestamp cache-buster so Cloudflare CDN / browser never serves stale data
            const sep = endpoint.includes('?') ? '&' : '?';
            const url = `${API_BASE}${endpoint}${sep}_t=${Date.now()}`;
            const res = await fetch(url, {
                headers: { 'Accept': 'application/json' },
                mode: 'cors'
            });
            if (!res.ok) return null;
            return await res.json();
        } catch (err) {
            console.debug(`[Codozent CMS] Hydration notice (${endpoint}):`, err.message);
            return null;
        }
    }

    // 1. Hydrate Page Text Fields (Hero headline, descriptions, badges, philosophy)
    async function hydratePageText() {
        const path = window.location.pathname.toLowerCase();
        let pageKey = 'index';
        if (path.includes('about.html')) pageKey = 'about';
        else if (path.includes('service.html')) pageKey = 'service';
        else if (path.includes('products.html')) pageKey = 'products';
        else if (path.includes('career.html')) pageKey = 'career';
        else if (path.includes('contact.html')) pageKey = 'contact';
        else if (path.includes('blog.html')) pageKey = 'blog';

        const data = await fetchJson(`/api/public/pages/${pageKey}`);
        if (!data || !data.success || !data.page || !data.page.fields) return;

        const fields = data.page.fields;

        if (pageKey === 'index') {
            // Hero top badge
            if (fields.hero_badge) {
                const val = fields.hero_badge.current_value || fields.hero_badge.draft_value;
                const badge = document.querySelector('span.pre-title');
                if (badge && val) badge.textContent = val;
            }

            // Hero main headline (preserves span styling)
            if (fields.hero_title) {
                const val = fields.hero_title.current_value || fields.hero_title.draft_value;
                const titleH1 = document.querySelector('h1.title');
                if (titleH1 && val) {
                    if (val.includes('Growing')) {
                        const parts = val.split('Growing');
                        titleH1.innerHTML = `${parts[0]}<span>Growing</span>${parts[1] || ''}`;
                    } else {
                        titleH1.textContent = val;
                    }
                }
            }

            // Hero description
            if (fields.hero_desc) {
                const val = fields.hero_desc.current_value || fields.hero_desc.draft_value;
                const descP = document.querySelector('div.banner-wrapper-one p');
                if (descP && val) descP.textContent = val;
            }

            // Hero CTA text
            if (fields.hero_cta_text) {
                const val = fields.hero_cta_text.current_value || fields.hero_cta_text.draft_value;
                const ctaBtn = document.querySelector('div.banner-wrapper-one a.rts-btn');
                if (ctaBtn && val) {
                    const icon = ctaBtn.querySelector('img');
                    ctaBtn.textContent = val + ' ';
                    if (icon) ctaBtn.appendChild(icon);
                }
            }

            // Philosophy Video text
            if (fields.video_title_1) {
                const val = fields.video_title_1.current_value || fields.video_title_1.draft_value;
                const vTitle = document.querySelector('div.title-video-top h2');
                if (vTitle && val) vTitle.textContent = val;
            }
            if (fields.video_desc) {
                const val = fields.video_desc.current_value || fields.video_desc.draft_value;
                const vDesc = document.querySelector('div.title-video-top p.disc');
                if (vDesc && val) vDesc.textContent = val;
            }

            // Services section heading & description
            if (fields.services_heading) {
                const val = fields.services_heading.current_value || fields.services_heading.draft_value;
                const sHeading = document.querySelector('div.service-area-one h2.title');
                if (sHeading && val) sHeading.textContent = val;
            }
            if (fields.services_subheading) {
                const val = fields.services_subheading.current_value || fields.services_subheading.draft_value;
                const sSub = document.querySelector('div.service-area-one p.disc');
                if (sSub && val) sSub.textContent = val;
            }

            // Footer Callout CTA
            if (fields.cta_box_title) {
                const val = fields.cta_box_title.current_value || fields.cta_box_title.draft_value;
                const ctaH2 = document.querySelector('div.cta-main-wrapper h2.title');
                if (ctaH2 && val) ctaH2.textContent = val;
            }
            if (fields.cta_box_desc) {
                const val = fields.cta_box_desc.current_value || fields.cta_box_desc.draft_value;
                const ctaP = document.querySelector('div.cta-main-wrapper p');
                if (ctaP && val) ctaP.textContent = val;
            }
        } else if (pageKey === 'about') {
            if (fields.hero_title) {
                const val = fields.hero_title.current_value || fields.hero_title.draft_value;
                const h1 = document.querySelector('h1.title');
                if (h1 && val) h1.textContent = val;
            }
            if (fields.hero_desc) {
                const val = fields.hero_desc.current_value || fields.hero_desc.draft_value;
                const p = document.querySelector('p.disc') || document.querySelector('p');
                if (p && val) p.textContent = val;
            }
        }
    }

    // 2. Hydrate Homepage Video Section
    async function hydrateVideoSection() {
        const videoContainer = document.querySelector('.image--large-video');
        if (!videoContainer) return;

        const data = await fetchJson('/api/public/video-section');
        if (!data || !data.success) return;

        // Update image & alt
        const img = videoContainer.querySelector('img.jarallax-img') || videoContainer.querySelector('img');
        if (img && data.image_url) {
            const cleanImg = cleanUrl(data.image_url);
            if (img.getAttribute('src') !== cleanImg) {
                img.src = cleanImg;
            }
            if (data.image_alt) {
                img.alt = data.image_alt;
            }
        }

        // Toggle video button based on setting
        const iconDiv = videoContainer.querySelector('.vedio-icone');
        const playBtns = videoContainer.querySelectorAll('.video-play-button, .play-video, .popup-video');

        if (data.video_enabled) {
            if (iconDiv) iconDiv.style.display = '';
            playBtns.forEach(btn => {
                btn.style.display = '';
                if (data.video_url && btn.tagName === 'A') {
                    btn.href = data.video_url;
                }
            });
        } else {
            // Video disabled: hide icon and play button completely
            if (iconDiv) iconDiv.style.display = 'none';
            playBtns.forEach(btn => {
                btn.style.display = 'none';
            });
        }
    }

    // 3. Hydrate Homepage Image Slots
    async function hydrateHomepageImages() {
        const data = await fetchJson('/api/public/homepage-images');
        if (!data || !data.success || !Array.isArray(data.images)) return;

        data.images.forEach(slot => {
            if (!slot.selector || !slot.current_src) return;
            try {
                const el = document.querySelector(slot.selector);
                if (el && el.tagName === 'IMG') {
                    const cleanSrc = cleanUrl(slot.current_src);
                    if (el.getAttribute('src') !== cleanSrc) {
                        el.src = cleanSrc;
                    }
                    if (slot.current_alt) {
                        el.alt = slot.current_alt;
                    }
                }
            } catch (e) {
                // Ignore selector error
            }
        });
    }

    // 4. Hydrate Work / Case Studies Items
    async function hydrateWorkItems() {
        const cards = document.querySelectorAll('div.single-case-studies');
        if (!cards || cards.length === 0) return;

        const data = await fetchJson('/api/public/work');
        if (!data || !data.success || !Array.isArray(data.work)) return;

        data.work.forEach((item, idx) => {
            if (idx >= cards.length) return;
            const card = cards[idx];
            if (!card) return;

            // Thumbnail
            const thumbLink = card.querySelector('a.thumbnail');
            const targetUrl = item.project_url || 'case-studies.html';
            if (thumbLink) thumbLink.href = targetUrl;

            const img = card.querySelector('img');
            if (img && item.image_url) {
                img.src = cleanUrl(item.image_url);
                if (item.image_alt) img.alt = item.image_alt;
            }

            // Category & Title
            const categorySpan = card.querySelector('div.inner-content span');
            if (categorySpan && item.category) categorySpan.textContent = item.category;

            const titleLink = card.querySelector('div.inner-content a h3.title, div.inner-content h3.title');
            if (titleLink && item.title) titleLink.textContent = item.title;

            // Button
            const btnLink = card.querySelector('a.rts-btn');
            if (btnLink) btnLink.href = targetUrl;
        });
    }

    // 5. Hydrate Latest Blog Insights
    async function hydrateBlogPosts() {
        const blogArea = document.querySelector('div.rts-blog-area');
        if (!blogArea) return;

        const cards = blogArea.querySelectorAll('div.single-blog-area-start');
        if (!cards || cards.length === 0) return;

        const data = await fetchJson('/api/public/blog');
        if (!data || !data.success || !Array.isArray(data.posts)) return;

        data.posts.slice(0, cards.length).forEach((post, idx) => {
            const card = cards[idx];
            if (!card) return;

            const targetUrl = `blog-details.html?slug=${post.slug}`;

            // Thumbnail
            const thumbLink = card.querySelector('a.thumbnail');
            if (thumbLink) thumbLink.href = targetUrl;

            const img = card.querySelector('a.thumbnail img');
            if (img && post.featured_image) {
                img.src = cleanUrl(post.featured_image);
                if (post.featured_image_alt) img.alt = post.featured_image_alt;
            }

            // Category & Title
            const topArea = card.querySelector('div.top-area');
            if (topArea) {
                const catSpan = topArea.querySelector('span');
                if (catSpan && post.category) catSpan.textContent = post.category;

                const titleA = topArea.querySelector('a');
                if (titleA) {
                    titleA.href = targetUrl;
                    const titleH3 = titleA.querySelector('h3.title');
                    if (titleH3 && post.title) titleH3.textContent = post.title;
                }

                const discP = topArea.querySelector('p.disc');
                if (discP && post.excerpt) discP.textContent = post.excerpt;

                const authorTitle = topArea.querySelector('div.author-area-info h6.title');
                if (authorTitle && post.author) authorTitle.textContent = post.author;

                const authorRole = topArea.querySelector('div.author-area-info span');
                if (authorRole && post.author_role) authorRole.textContent = post.author_role;
            }
        });
    }

    // 6. Hydrate Careers / Jobs
    async function hydrateJobs() {
        const jobContainer = document.querySelector('div.job-openings-container, div.career-accordion');
        if (!jobContainer) return;

        const data = await fetchJson('/api/public/jobs');
        if (!data || !data.success) return;
        // Jobs list hydration handled if container exists
    }

    function init() {
        hydratePageText();
        hydrateVideoSection();
        hydrateHomepageImages();
        hydrateWorkItems();
        hydrateBlogPosts();
        hydrateJobs();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
