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
        const path = window.location.pathname.toLowerCase().replace(/\.html$/, '');
        let pageKey = 'index';
        if (path.endsWith('/about')) pageKey = 'about';
        else if (path.endsWith('/service')) pageKey = 'service';
        else if (path.endsWith('/products')) pageKey = 'products';
        else if (path.endsWith('/career')) pageKey = 'career';
        else if (path.endsWith('/contact')) pageKey = 'contact';
        else if (path.endsWith('/blog')) pageKey = 'blog';

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

    // 3. Hydrate All Website Image Slots (Homepage + Inner Pages + Background Banners)
    async function hydrateHomepageImages() {
        const data = await fetchJson('/api/public/homepage-images');
        if (!data || !data.success || !Array.isArray(data.images)) return;

        const rawPath = (window.location.pathname.split('/').pop() || 'index').toLowerCase().replace(/\.html$/, '');
        const pageKey = rawPath === '' ? 'index' : rawPath;

        data.images.forEach(slot => {
            if (!slot.selector || !slot.current_src) return;
            const slotPage = (slot.page_path || 'index.html').toLowerCase().replace(/\.html$/, '');
            if (slotPage !== '*' && slotPage !== pageKey) return;

            try {
                const els = document.querySelectorAll(slot.selector);
                if (!els || els.length === 0) return;
                const cleanSrc = cleanUrl(slot.current_src);

                els.forEach(el => {
                    const applyImage = () => {
                        if (slot.target_type === 'bg' || el.tagName !== 'IMG') {
                            el.style.setProperty('background-image', `url('${cleanSrc}')`, 'important');
                            el.style.backgroundSize = 'cover';
                            el.style.backgroundPosition = 'center';
                            const jContainer = el.querySelector('[id^="jarallax-container"]');
                            if (jContainer) {
                                const jImg = jContainer.querySelector('img');
                                if (jImg) jImg.src = cleanSrc;
                                const jDiv = jContainer.querySelector('div');
                                if (jDiv) jDiv.style.setProperty('background-image', `url('${cleanSrc}')`, 'important');
                            }
                        } else {
                            if (el.getAttribute('src') !== cleanSrc) {
                                el.src = cleanSrc;
                            }
                            if (slot.current_alt) {
                                el.alt = slot.current_alt;
                            }
                        }
                    };
                    applyImage();
                    setTimeout(applyImage, 350);
                    window.addEventListener('load', applyImage, { once: true });
                });
            } catch (e) {
                // Ignore selector error
            }
        });
    }

    // 4. Hydrate Work / Case Studies Items
    async function hydrateWorkItems() {
        const cards = Array.from(document.querySelectorAll('div.single-case-studies'));
        if (!cards || cards.length === 0) return;

        const data = await fetchJson('/api/public/work');
        if (!data || !data.success || !Array.isArray(data.work) || data.work.length === 0) return;

        cards.forEach((card, idx) => {
            const col = card.closest('[class*="col-"]') || card;
            if (idx >= data.work.length) {
                col.style.display = 'none';
                return;
            }
            col.style.display = '';
            const item = data.work[idx];

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

        const cards = Array.from(blogArea.querySelectorAll('div.single-blog-area-start'));
        if (!cards || cards.length === 0) return;

        const data = await fetchJson('/api/public/blog');
        if (!data || !data.success || !Array.isArray(data.posts) || data.posts.length === 0) return;

        const cleanPath = window.location.pathname.toLowerCase().replace(/\.html$/, '');
        const isBlogListPage = cleanPath.endsWith('/blog') || cleanPath.endsWith('/blog-grid');
        const rowContainer = cards[0].closest('.row');
        if (isBlogListPage && rowContainer && data.posts.length > cards.length) {
            const templateCol = cards[cards.length - 1].closest('[class*="col-"]');
            if (templateCol) {
                while (cards.length < data.posts.length) {
                    const cloneCol = templateCol.cloneNode(true);
                    rowContainer.appendChild(cloneCol);
                    const newCard = cloneCol.querySelector('div.single-blog-area-start');
                    if (newCard) cards.push(newCard);
                }
            }
        }

        cards.forEach((card, idx) => {
            const col = card.closest('[class*="col-"]') || card;
            if (idx >= data.posts.length) {
                col.style.display = 'none';
                return;
            }
            col.style.display = '';
            const post = data.posts[idx];
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
        const openingsSection = document.getElementById('openings');
        const jobContainer = openingsSection ? openingsSection.querySelector('.row.g-5') : document.querySelector('div.job-openings-container, div.career-accordion');
        if (!jobContainer) return;

        const data = await fetchJson('/api/public/jobs');
        if (!data || !data.success || !Array.isArray(data.jobs) || data.jobs.length === 0) return;

        jobContainer.classList.remove('justify-content-center');
        jobContainer.innerHTML = data.jobs.map(function(job) {
            const applyUrl = (job.apply_url && !job.apply_url.includes('apply.html') && (job.apply_url.startsWith('http://') || job.apply_url.startsWith('https://') || job.apply_url.startsWith('mailto:')))
                ? job.apply_url
                : `apply.html?job_id=${encodeURIComponent(job.id)}&role=${encodeURIComponent(job.title || '')}`;
            const applyTarget = (applyUrl.startsWith('http://') || applyUrl.startsWith('https://')) ? ' target="_blank" rel="noopener"' : '';
            const safeDesc = (job.description || '').replace(/<[^>]*>/g, '').slice(0, 180);

            return `
            <div class="col-lg-6 col-md-6 col-12">
                <div class="single-job-opening-card" style="padding: 32px; border: 1px solid #E2E8F0; border-radius: 12px; background: #fff; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px;">
                            <span style="font-size: 12px; font-weight: 600; color: #1363DF; background: #EFF6FF; padding: 4px 12px; border-radius: 20px; text-transform: uppercase;">${job.department || 'Engineering'}</span>
                            <span style="font-size: 13px; color: #64748B;">${job.employment_type || 'Full-time'} • ${job.location || 'Remote'}</span>
                        </div>
                        <h4 class="title" style="margin-bottom: 10px;">
                            <a href="career-single.html?id=${encodeURIComponent(job.id)}" style="color: #0F172A; text-decoration: none;">${job.title}</a>
                        </h4>
                        ${job.salary ? `<div style="font-size: 14px; font-weight: 600; color: #059669; margin-bottom: 10px;">${job.salary}</div>` : ''}
                        <p style="font-size: 15px; color: #475569; line-height: 1.6; margin-bottom: 20px;">${safeDesc}${safeDesc.length >= 180 ? '...' : ''}</p>
                    </div>
                    <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                        <a class="rts-btn btn-primary" href="career-single.html?id=${encodeURIComponent(job.id)}" style="padding: 12px 22px; font-size: 14px;">View Details</a>
                        <a class="rts-btn btn-border" href="${applyUrl}"${applyTarget} style="padding: 12px 22px; font-size: 14px;">${job.apply_label || 'Apply Now'}</a>
                    </div>
                </div>
            </div>`;
        }).join('');
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
