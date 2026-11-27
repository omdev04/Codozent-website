/**
 * Codozent CMS Admin Application Logic
 */
const app = {
    currentUser: null,
    currentTab: 'dashboard',
    allJobs: [],
    allPosts: [],
    allImages: [],
    allWork: [],
    allMedia: [],
    currentWorkFilter: 'all',
    pagesList: [],
    selectedPageKey: null,
    selectedPageData: null,
    currentPickerOptions: null,

    formatImageUrl(url) {
        if (!url) return '';
        url = String(url).trim();
        if (url.startsWith('res.cloudinary.com')) {
            return `https://${url}`;
        }
        if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
            return url;
        }
        if (url.startsWith('/')) {
            return url;
        }
        return `/${url}`;
    },

    init() {
        this.bindEvents();
        this.checkAuth();
        window.addEventListener('hashchange', () => {
            const h = window.location.hash.replace('#', '');
            if (h) this.switchTab(h);
        });
    },

    bindEvents() {
        // Tab routing via hash or click
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const tab = item.getAttribute('data-tab');
                this.switchTab(tab);
            });
        });

        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.handleLogout());
        }

        // Job form real-time preview inputs
        ['job-title', 'job-dept', 'job-loc', 'job-type', 'job-desc', 'job-apply-label'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', () => this.updateJobPreview());
            }
        });

        // Work item real-time preview inputs
        ['work-title', 'work-category', 'work-image-url', 'work-desc'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', () => this.updateWorkPreview());
            }
        });
    },

    async checkAuth() {
        // Check if token was passed in URL query param
        const urlParams = new URLSearchParams(window.location.search);
        const queryToken = urlParams.get('token');
        if (queryToken) {
            document.cookie = `admin_token=${queryToken}; path=/; max-age=43200; SameSite=Lax`;
        }

        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const data = await res.json();
                if (data.user && data.user.role === 'admin') {
                    this.currentUser = data.user;
                    this.setupUserProfile();
                    const hash = window.location.hash.replace('#', '');
                    if (hash) {
                        this.switchTab(hash);
                    } else {
                        this.loadDashboardData();
                    }
                } else {
                    window.location.href = '/admin/login';
                }
            } else {
                window.location.href = '/admin/login';
            }
        } catch (err) {
            window.location.href = '/admin/login';
        }
    },

    setupUserProfile() {
        if (this.currentUser) {
            document.getElementById('user-display-name').textContent = this.currentUser.full_name || 'Admin';
            document.getElementById('user-display-email').textContent = this.currentUser.email || '';
        }
    },

    async handleLogout() {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
        } catch (e) {}
        this.currentUser = null;
        window.location.href = '/admin/login';
    },

    switchTab(tabId) {
        this.currentTab = tabId;
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.getAttribute('data-tab') === tabId);
        });
        document.querySelectorAll('.tab-pane').forEach(el => {
            el.classList.toggle('active', el.id === `tab-${tabId}`);
        });

        // Set topbar title
        const titles = {
            dashboard: ['Dashboard Overview', 'System metrics and operational status'],
            careers: ['Careers & Job Management', 'Manage job openings and application URLs (Highest Priority)'],
            images: ['Homepage Images & Work', 'Manage featured portfolio work and fixed homepage image slots with exact aspect ratios'],
            pages: ['Page Content Management', 'Edit live text fields while preserving layout and structure'],
            blog: ['Blog & Engineering Insights', 'Publish, draft, and archive engineering perspectives'],
            media: ['Media Asset Library', 'Upload and manage images with Cloudinary delivery and size safety'],
            users: ['User Management', 'Manage team members, roles, and administrative access permissions'],
            account: ['Admin Account Settings', 'Manage your administrator password and security']
        };

        if (titles[tabId]) {
            document.getElementById('page-title').textContent = titles[tabId][0];
            document.getElementById('page-subtitle').textContent = titles[tabId][1];
        }

        // Load tab-specific data
        if (tabId === 'dashboard') this.loadDashboardData();
        if (tabId === 'careers') this.loadJobs();
        if (tabId === 'images') {
            this.loadWorkItems();
            this.loadHomepageImages();
            this.loadVideoSection();
        }
        if (tabId === 'pages') this.loadPagesList();
        if (tabId === 'blog') this.loadBlogPosts();
        if (tabId === 'media') this.loadMediaLibrary();
        if (tabId === 'users') this.loadUsers();
    },

    // ----------------- DASHBOARD -----------------
    async loadDashboardData() {
        try {
            const res = await fetch('/api/admin/stats');
            if (res.ok) {
                const data = await res.json();
                const s = data.stats;
                document.getElementById('stat-published-jobs').textContent = s.published_jobs;
                document.getElementById('badge-jobs').textContent = s.published_jobs;
                document.getElementById('stat-published-blogs').textContent = s.published_blogs;
                document.getElementById('badge-blog').textContent = s.published_blogs;
                document.getElementById('stat-pages-count').textContent = s.pages;
                document.getElementById('stat-images-count').textContent = s.images;

                const jobStatusEl = document.getElementById('stat-job-status');
                if (s.published_jobs > 0) {
                    jobStatusEl.textContent = `Public site: ${s.published_jobs} open position(s) live`;
                    jobStatusEl.style.color = '#10B981';
                } else {
                    jobStatusEl.textContent = 'Public site: "No current openings" state';
                    jobStatusEl.style.color = '#64748B';
                }
            }
        } catch (err) {
            logger.error(err);
        }
    },

    // ----------------- CAREERS & JOBS (HIGHEST PRIORITY) -----------------
    async loadJobs(statusFilter = 'all') {
        const tbody = document.getElementById('jobs-table-body');
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4"><i class="fa-regular fa-spinner fa-spin"></i> Loading openings...</td></tr>';

        try {
            const res = await fetch(`/api/admin/jobs?status=${statusFilter}`);
            const data = await res.json();
            this.allJobs = data.jobs || [];

            // Update banner
            const publishedCount = this.allJobs.filter(j => j.status === 'published').length;
            const banner = document.getElementById('career-status-text');
            if (publishedCount > 0) {
                banner.innerHTML = `<strong>Public Status:</strong> There are currently <strong>${publishedCount}</strong> active job(s) live on the public Careers page (<a href="/career.html#openings" target="_blank" style="color: #1363DF; text-decoration: underline;">View Live</a>).`;
            } else {
                banner.innerHTML = `<strong>Public Status:</strong> No jobs are currently published. The public Careers page is actively displaying the honest <strong>"No Current Openings"</strong> empty state card (<a href="/career.html#openings" target="_blank" style="color: #1363DF; text-decoration: underline;">Verify Live</a>).`;
            }

            if (this.allJobs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No job openings found in this category. Click "+ Add Job Opening" to create one.</td></tr>';
                return;
            }

            tbody.innerHTML = this.allJobs.map(job => {
                const statusBadges = {
                    published: '<span class="badge badge-success"><i class="fa-regular fa-check"></i> Published (Live)</span>',
                    draft: '<span class="badge badge-warning"><i class="fa-regular fa-pencil"></i> Draft (Private)</span>',
                    closed: '<span class="badge badge-muted"><i class="fa-regular fa-ban"></i> Closed</span>'
                };
                const badge = statusBadges[job.status] || `<span class="badge badge-muted">${job.status}</span>`;

                return `
                <tr>
                    <td>
                        <strong style="color: #081836; font-size: 14px;">${this.escapeHtml(job.title)}</strong>
                        <div style="font-size: 12px; color: #64748B;">${this.escapeHtml(job.department)}</div>
                    </td>
                    <td>
                        <div>${this.escapeHtml(job.location)}</div>
                        <span class="badge badge-primary">${this.escapeHtml(job.employment_type)}</span>
                    </td>
                    <td>
                        <a href="${this.escapeHtml(job.apply_url)}" target="_blank" rel="noopener noreferrer" style="color: #1363DF; font-size: 12px; text-decoration: underline; max-width: 220px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${this.escapeHtml(job.apply_url)}
                        </a>
                    </td>
                    <td>${badge}</td>
                    <td>
                        <div style="display: flex; gap: 6px;">
                            ${job.status !== 'published' ? 
                                `<button class="btn btn-outline btn-sm" title="Publish live" onclick="app.publishJob(${job.id})"><i class="fa-regular fa-upload text-success"></i> Publish</button>` :
                                `<button class="btn btn-outline btn-sm" title="Move to draft" onclick="app.unpublishJob(${job.id})"><i class="fa-regular fa-eye-slash"></i> Unpublish</button>`
                            }
                            <button class="btn btn-outline btn-sm" onclick="app.showEditJobModal(${job.id})"><i class="fa-regular fa-pen"></i></button>
                            <button class="btn btn-outline btn-sm" onclick="app.closeJob(${job.id})" title="Close job"><i class="fa-regular fa-lock"></i></button>
                            <button class="btn btn-danger btn-sm" onclick="app.deleteJob(${job.id})"><i class="fa-regular fa-trash"></i></button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');
        } catch (err) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-danger">Failed to load jobs from server.</td></tr>';
        }
    },

    filterJobs(status) {
        document.querySelectorAll('[data-job-filter]').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-job-filter') === status);
        });
        this.loadJobs(status);
    },

    showAddJobModal() {
        document.getElementById('job-modal-title').textContent = 'Add New Job Opening';
        document.getElementById('job-form').reset();
        document.getElementById('job-id').value = '';
        document.getElementById('job-apply-label').value = 'Apply Now at Codozent';
        document.getElementById('job-apply-url').value = 'apply.html';
        document.getElementById('job-status').value = 'published';
        this.updateJobPreview();
        this.openModal('job-modal');
    },

    async showEditJobModal(jobId) {
        try {
            const res = await fetch(`/api/admin/jobs/${jobId}`);
            const data = await res.json();
            const job = data.job;

            document.getElementById('job-modal-title').textContent = 'Edit Job Opening';
            document.getElementById('job-id').value = job.id;
            document.getElementById('job-title').value = job.title;
            document.getElementById('job-dept').value = job.department;
            document.getElementById('job-loc').value = job.location;
            document.getElementById('job-type').value = job.employment_type;
            document.getElementById('job-salary').value = job.salary || '';
            document.getElementById('job-desc').value = job.description;
            document.getElementById('job-responsibilities').value = job.responsibilities || '';
            document.getElementById('job-quals').value = job.qualifications || '';
            document.getElementById('job-skills').value = job.skills || '';
            document.getElementById('job-deadline').value = job.deadline || '';
            document.getElementById('job-apply-label').value = job.apply_label || 'Apply Now at Codozent';
            document.getElementById('job-apply-url').value = job.apply_url || 'apply.html';
            document.getElementById('job-status').value = job.status;

            this.updateJobPreview();
            this.openModal('job-modal');
        } catch (e) {
            this.showToast('Failed to load job details', 'error');
        }
    },

    updateJobPreview() {
        const title = document.getElementById('job-title').value || 'Job Title';
        const dept = document.getElementById('job-dept').value || 'Department';
        const loc = document.getElementById('job-loc').value || 'Location';
        const type = document.getElementById('job-type').value || 'Full-time';
        const desc = document.getElementById('job-desc').value || 'Brief job summary...';
        const applyLabel = document.getElementById('job-apply-label').value || 'Apply for Role';

        document.getElementById('prev-title').textContent = title;
        document.getElementById('prev-dept').innerHTML = `<i class="fa-regular fa-briefcase"></i> ${dept}`;
        document.getElementById('prev-loc').innerHTML = `<i class="fa-regular fa-location-dot"></i> ${loc}`;
        document.getElementById('prev-type').innerHTML = `<i class="fa-regular fa-clock"></i> ${type}`;
        document.getElementById('prev-desc').textContent = desc;
        document.getElementById('prev-btn').innerHTML = `${applyLabel} <i class="fa-regular fa-arrow-up-right"></i>`;
    },

    async handleJobSubmit(e) {
        e.preventDefault();
        const id = document.getElementById('job-id').value;
        const payload = {
            title: document.getElementById('job-title').value.trim(),
            department: document.getElementById('job-dept').value.trim(),
            location: document.getElementById('job-loc').value.trim(),
            employment_type: document.getElementById('job-type').value,
            salary: document.getElementById('job-salary').value.trim(),
            description: document.getElementById('job-desc').value.trim(),
            responsibilities: document.getElementById('job-responsibilities').value.trim(),
            qualifications: document.getElementById('job-quals').value.trim(),
            skills: document.getElementById('job-skills').value.trim(),
            deadline: document.getElementById('job-deadline').value,
            apply_label: document.getElementById('job-apply-label').value.trim() || 'Apply Now at Codozent',
            apply_url: document.getElementById('job-apply-url').value.trim() || 'apply.html',
            status: document.getElementById('job-status').value
        };

        const url = payload.apply_url;
        if (!url.startsWith('https://') && !url.startsWith('http://') && !url.startsWith('mailto:') && !url.startsWith('apply.html')) {
            this.showToast('Validation Error: Apply link must be apply.html or start with https://, http://, or mailto:', 'error');
            return;
        }

        const submitBtn = document.getElementById('job-submit-btn');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-regular fa-spinner fa-spin"></i> Saving...';

        try {
            const urlEndpoint = id ? `/api/admin/jobs/${id}` : '/api/admin/jobs';
            const method = id ? 'PUT' : 'POST';

            const res = await fetch(urlEndpoint, {
                method,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (res.ok && data.success) {
                this.closeModal('job-modal');
                this.showToast(data.message || 'Job saved successfully.', 'success');
                this.loadJobs();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Failed to save job opening.', 'error');
            }
        } catch (err) {
            this.showToast('Network error while saving job opening.', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Job Opening';
        }
    },

    async publishJob(jobId) {
        try {
            const res = await fetch(`/api/admin/jobs/${jobId}/publish`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                this.loadJobs();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Could not publish job.', 'error');
            }
        } catch (e) {
            this.showToast('Server error while publishing job.', 'error');
        }
    },

    async unpublishJob(jobId) {
        try {
            const res = await fetch(`/api/admin/jobs/${jobId}/unpublish`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'info');
                this.loadJobs();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while unpublishing job.', 'error');
        }
    },

    async closeJob(jobId) {
        if (!confirm('Are you sure you want to mark this opening as closed? It will be removed from the public website.')) return;
        try {
            const res = await fetch(`/api/admin/jobs/${jobId}/close`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'info');
                this.loadJobs();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while closing job.', 'error');
        }
    },

    async deleteJob(jobId) {
        if (!confirm('Are you sure you want to permanently delete this job listing?')) return;
        try {
            const res = await fetch(`/api/admin/jobs/${jobId}`, { method: 'DELETE' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                this.loadJobs();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while deleting job.', 'error');
        }
    },

    // ----------------- HOMEPAGE WORK & PORTFOLIO ITEMS -----------------
    switchSubTab(subtabId) {
        document.querySelectorAll('#tab-images .subnav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-subtab') === subtabId);
        });
        const workSub = document.getElementById('subtab-work-items');
        const slotsSub = document.getElementById('subtab-image-slots');
        const videoSub = document.getElementById('subtab-video-section');

        if (workSub) workSub.style.display = subtabId === 'work-items' ? 'block' : 'none';
        if (slotsSub) slotsSub.style.display = subtabId === 'image-slots' ? 'block' : 'none';
        if (videoSub) videoSub.style.display = subtabId === 'video-section' ? 'block' : 'none';

        if (subtabId === 'work-items') {
            this.loadWorkItems();
        } else if (subtabId === 'image-slots') {
            this.loadHomepageImages();
        } else if (subtabId === 'video-section') {
            this.loadVideoSection();
        }
    },

    // ----------------- HOMEPAGE VIDEO SHOWCASE -----------------
    videoSectionData: {
        video_enabled: true,
        video_url: 'https://www.youtube.com/watch?v=vZE0j_WCRvI',
        image_url: 'assets/images/video/01.webp',
        image_alt: 'Engineering Process'
    },

    async loadVideoSection() {
        try {
            const res = await fetch('/api/admin/video-section');
            const data = await res.json();
            if (data.success && data.video_section) {
                this.videoSectionData = data.video_section;
                const v = this.videoSectionData;

                const urlEl = document.getElementById('video-section-url');
                const imgEl = document.getElementById('video-section-image');
                const altEl = document.getElementById('video-section-alt');

                if (urlEl) urlEl.value = v.video_url || 'https://www.youtube.com/watch?v=vZE0j_WCRvI';
                if (imgEl) imgEl.value = v.image_url || 'assets/images/video/01.webp';
                if (altEl) altEl.value = v.image_alt || 'Engineering Process';

                this.setVideoMode(Boolean(v.video_enabled));
                this.updateVideoPreview();
            }
        } catch (err) {
            console.error('Failed to load video section settings:', err);
        }
    },

    setVideoMode(enabled) {
        const radioOn = document.getElementById('radio-video-on');
        const radioOff = document.getElementById('radio-video-off');
        const cardOn = document.getElementById('mode-video-card');
        const cardOff = document.getElementById('mode-image-card');
        const badgeOn = document.getElementById('badge-mode-video');
        const badgeOff = document.getElementById('badge-mode-image');
        const urlGroup = document.getElementById('group-video-url');
        const urlHint = document.getElementById('video-url-status-hint');
        const playBtn = document.getElementById('video-preview-play-btn');
        const pill = document.getElementById('video-preview-image-only-pill');
        const badge = document.getElementById('video-status-badge');
        const indicator = document.getElementById('preview-mode-indicator');

        if (radioOn) radioOn.checked = enabled;
        if (radioOff) radioOff.checked = !enabled;

        if (cardOn) {
            if (enabled) {
                cardOn.classList.add('active-video');
            } else {
                cardOn.classList.remove('active-video');
            }
        }
        if (cardOff) {
            if (!enabled) {
                cardOff.classList.add('active-image');
            } else {
                cardOff.classList.remove('active-image');
            }
        }

        if (badgeOn) badgeOn.style.display = enabled ? 'inline-block' : 'none';
        if (badgeOff) badgeOff.style.display = !enabled ? 'inline-block' : 'none';

        if (urlGroup) {
            urlGroup.style.opacity = enabled ? '1' : '0.6';
        }
        if (urlHint) {
            urlHint.textContent = enabled ? 'Active in Video Mode' : '(Disabled in Image Only mode)';
            urlHint.style.color = enabled ? '#0F50BC' : '#94A3B8';
        }

        if (playBtn) {
            playBtn.style.display = enabled ? 'flex' : 'none';
        }

        if (pill) {
            pill.style.display = enabled ? 'none' : 'flex';
        }

        if (badge) {
            badge.innerHTML = enabled
                ? '<span class="badge badge-primary" style="font-size: 13px; padding: 6px 14px;"><i class="fa-solid fa-circle-play mr-1"></i> Video Mode Active</span>'
                : '<span class="badge badge-muted" style="font-size: 13px; padding: 6px 14px; background: #64748B; color: #fff;"><i class="fa-regular fa-image mr-1"></i> Static Image Only Mode</span>';
        }

        if (indicator) {
            indicator.textContent = enabled ? 'Mode: Video Active (Play Button Enabled)' : 'Mode: Static Image Only (No Play Button)';
        }
    },

    updateVideoPreview() {
        const imgInput = document.getElementById('video-section-image');
        const previewImg = document.getElementById('video-preview-img');
        if (imgInput && previewImg) {
            const raw = (imgInput.value || 'assets/images/video/01.webp').trim();
            previewImg.src = this.formatImageUrl(raw);
        }
    },

    testVideoLink() {
        const urlInput = document.getElementById('video-section-url');
        const url = (urlInput ? urlInput.value : '').trim() || 'https://www.youtube.com/watch?v=vZE0j_WCRvI';
        window.open(url, '_blank');
    },

    openMediaPickerForVideo() {
        this.openUniversalMediaPicker({
            title: 'Choose Video Showcase Background Image',
            targetInputId: 'video-section-image',
            targetAltId: 'video-section-alt',
            onSelect: () => this.updateVideoPreview()
        });
    },

    selectVideoImage(url, alt) {
        const imgInput = document.getElementById('video-section-image');
        const altInput = document.getElementById('video-section-alt');
        if (imgInput) imgInput.value = url;
        if (altInput && alt && alt !== 'Image Asset') altInput.value = alt;
        this.updateVideoPreview();
        this.closeUniversalMediaPicker();
        this.showToast('Showcase image updated from Media Library.', 'info');
    },

    closeVideoMediaPicker() {
        this.closeUniversalMediaPicker();
    },

    async saveVideoSection(e) {
        if (e && e.preventDefault) {
            e.preventDefault();
        }

        const radioOn = document.getElementById('radio-video-on');
        const urlInput = document.getElementById('video-section-url');
        const imgInput = document.getElementById('video-section-image');
        const altInput = document.getElementById('video-section-alt');
        const btnSave = document.getElementById('btn-save-video');

        const video_enabled = radioOn ? radioOn.checked : true;
        const video_url = urlInput ? urlInput.value.trim() : 'https://www.youtube.com/watch?v=vZE0j_WCRvI';
        const image_url = imgInput ? imgInput.value.trim() : 'assets/images/video/01.webp';
        const image_alt = altInput ? altInput.value.trim() : 'Engineering Process';

        if (video_enabled && !video_url) {
            this.showToast('Please enter a valid YouTube video URL when Video Mode is enabled.', 'error');
            if (urlInput) urlInput.focus();
            return;
        }

        if (btnSave) {
            btnSave.disabled = true;
            btnSave.innerHTML = '<i class="fa-regular fa-spinner fa-spin mr-1"></i> Saving & Publishing...';
        }

        try {
            const res = await fetch('/api/admin/video-section', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_enabled: video_enabled,
                    video_url: video_url,
                    image_url: image_url,
                    image_alt: image_alt
                })
            });

            let data;
            try {
                data = await res.json();
            } catch (jsonErr) {
                data = { detail: `Server response error (${res.status} ${res.statusText})` };
            }

            if (res.ok && data.success) {
                this.showToast(data.message || 'Video section updated & published successfully!', 'success');
                this.videoSectionData = data.video_section;
                this.setVideoMode(video_enabled);
                this.updateVideoPreview();
            } else {
                this.showToast(data.detail || data.message || `Failed to update video section (HTTP ${res.status}).`, 'error');
            }
        } catch (err) {
            console.error('Save video section error:', err);
            this.showToast('Network error while saving video section: ' + (err.message || 'Check connection.'), 'error');
        } finally {
            if (btnSave) {
                btnSave.disabled = false;
                btnSave.innerHTML = '<i class="fa-regular fa-floppy-disk mr-1"></i> Save &amp; Publish Video Section';
            }
        }
    },

    async loadWorkItems() {
        const tbody = document.getElementById('work-table-body');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><i class="fa-regular fa-spinner fa-spin"></i> Loading portfolio work...</td></tr>';

        try {
            const res = await fetch('/api/admin/work');
            const data = await res.json();
            this.allWork = data.items || [];
            this.renderWorkTable();
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-danger text-center py-4">Failed to load work items.</td></tr>';
        }
    },

    filterWork(status) {
        this.currentWorkFilter = status;
        document.querySelectorAll('[data-work-filter]').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-work-filter') === status);
        });
        this.renderWorkTable();
    },

    renderWorkTable() {
        const tbody = document.getElementById('work-table-body');
        if (!tbody) return;

        let filtered = this.allWork;
        if (this.currentWorkFilter !== 'all') {
            filtered = this.allWork.filter(w => w.status === this.currentWorkFilter);
        }

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No portfolio items found. Click "+ Add New Work Item" above to add one.</td></tr>';
            return;
        }

        tbody.innerHTML = filtered.map(item => {
            const isLive = item.status === 'published';
            const badge = isLive ? 
                '<span class="badge badge-success"><i class="fa-regular fa-check"></i> Published</span>' : 
                '<span class="badge badge-warning"><i class="fa-regular fa-clock"></i> Draft</span>';

            const isCloudinary = (item.storage_provider === 'cloudinary') || (item.image_url && item.image_url.includes('cloudinary'));
            const providerBadge = isCloudinary ? 
                '<span class="badge badge-purple" style="font-size:10px; margin-left:4px;"><i class="fa-regular fa-cloud"></i> Cloudinary</span>' : '';

            let rawUrl = (item.image_url || '').trim();
            let imgSrc = rawUrl;
            if (!rawUrl) {
                imgSrc = '/assets/images/case-studies/01.webp';
            } else if (rawUrl.startsWith('res.cloudinary.com')) {
                imgSrc = `https://${rawUrl}`;
            } else if (!rawUrl.startsWith('http') && !rawUrl.startsWith('/')) {
                imgSrc = `/${rawUrl}`;
            }

            return `
            <tr>
                <td style="width: 100px;">
                    <div style="width: 80px; height: 50px; border-radius: 6px; overflow: hidden; background: #081836; border: 1px solid #E2E8F0;">
                        <img src="${imgSrc}" alt="${this.escapeHtml(item.image_alt || item.title)}" style="width: 100%; height: 100%; object-fit: cover;">
                    </div>
                </td>
                <td>
                    <strong style="color: #081836; font-size: 14px;">${this.escapeHtml(item.title)}</strong>
                    <div style="font-size: 12px; color: #1363DF; font-weight: 500;">${this.escapeHtml(item.category)}</div>
                </td>
                <td>
                    <code style="font-size: 12px; background: #F1F5F9; padding: 2px 6px; border-radius: 4px;">${this.escapeHtml(item.project_url || 'case-studies.html')}</code>
                </td>
                <td>
                    <span style="font-weight: 600; color: #64748B;">#${item.display_order}</span>
                </td>
                <td>
                    ${badge}
                    ${providerBadge}
                </td>
                <td class="text-right">
                    <div style="display: flex; gap: 6px; justify-content: flex-end;">
                        ${isLive ?
                            `<button class="btn btn-outline btn-sm" title="Unpublish from website" onclick="app.togglePublishWork(${item.id}, 'published')"><i class="fa-regular fa-eye-slash"></i> Unpublish</button>` :
                            `<button class="btn btn-outline btn-sm" title="Publish to live website" onclick="app.togglePublishWork(${item.id}, 'draft')"><i class="fa-regular fa-arrow-up-from-bracket text-success"></i> Publish</button>`
                        }
                        <button class="btn btn-outline btn-sm" title="Edit work item" onclick="app.showEditWorkModal(${item.id})"><i class="fa-regular fa-pen"></i></button>
                        <button class="btn btn-outline btn-sm" title="Delete work item" onclick="app.deleteWorkItem(${item.id})"><i class="fa-regular fa-trash text-danger"></i></button>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
    },

    showAddWorkModal() {
        document.getElementById('work-modal-title').innerHTML = '<i class="fa-regular fa-briefcase mr-2" style="color: #1363DF;"></i> Add Work / Portfolio Item';
        document.getElementById('work-id').value = '';
        document.getElementById('work-title').value = '';
        document.getElementById('work-category').value = '';
        document.getElementById('work-route').value = 'case-studies.html';
        document.getElementById('work-order').value = (this.allWork.length + 1);
        document.getElementById('work-status').value = 'published';
        document.getElementById('work-image-url').value = 'assets/images/case-studies/01.webp';
        document.getElementById('work-image-alt').value = 'Codozent Engineering Portfolio Project';
        document.getElementById('work-desc').value = '';
        document.getElementById('work-submit-btn').textContent = 'Create Work Item';
        this.updateWorkPreview();
        this.openModal('work-modal');
    },

    showEditWorkModal(id) {
        const item = this.allWork.find(w => w.id === id);
        if (!item) return;

        document.getElementById('work-modal-title').innerHTML = '<i class="fa-regular fa-pen-to-square mr-2" style="color: #1363DF;"></i> Edit Work / Portfolio Item';
        document.getElementById('work-id').value = item.id;
        document.getElementById('work-title').value = item.title;
        document.getElementById('work-category').value = item.category;
        document.getElementById('work-route').value = item.project_url || 'case-studies.html';
        document.getElementById('work-order').value = item.display_order;
        document.getElementById('work-status').value = item.status;
        document.getElementById('work-image-url').value = item.image_url;
        document.getElementById('work-image-alt').value = item.image_alt || item.title;
        document.getElementById('work-desc').value = item.description || '';
        document.getElementById('work-submit-btn').textContent = 'Update Work Item';
        this.updateWorkPreview();
        this.openModal('work-modal');
    },

    openMediaPickerForWork() {
        this.openUniversalMediaPicker({
            title: 'Choose Work / Portfolio Image',
            targetInputId: 'work-image-url',
            targetAltId: 'work-image-alt',
            onSelect: () => this.updateWorkPreview()
        });
    },

    updateWorkPreview() {
        const title = document.getElementById('work-title')?.value.trim() || 'High-Performance Responsive Web Portals';
        const cat = document.getElementById('work-category')?.value.trim() || 'Website Development, Performance';
        let rawImg = (document.getElementById('work-image-url')?.value || '').trim();
        if (!rawImg) {
            rawImg = 'assets/images/case-studies/01.webp';
        }

        const imgSrc = this.formatImageUrl(rawImg);

        const prevTitle = document.getElementById('work-prev-title');
        const prevCat = document.getElementById('work-prev-cat');
        const prevImg = document.getElementById('work-prev-img');

        if (prevTitle) prevTitle.textContent = title;
        if (prevCat) prevCat.textContent = cat;
        if (prevImg) {
            prevImg.onerror = () => {
                prevImg.style.opacity = '0.4';
                prevImg.title = 'Image could not be loaded. Please check the URL.';
            };
            prevImg.onload = () => {
                prevImg.style.opacity = '1';
                prevImg.title = 'Image loaded successfully';
            };
            prevImg.src = imgSrc;
        }
    },

    async handleWorkSubmit(e) {
        e.preventDefault();
        const id = document.getElementById('work-id').value;
        let imgUrl = document.getElementById('work-image-url').value.trim();
        if (imgUrl.startsWith('res.cloudinary.com')) {
            imgUrl = `https://${imgUrl}`;
        }
        const isCloudinary = imgUrl.toLowerCase().includes('cloudinary');
        const payload = {
            title: document.getElementById('work-title').value.trim(),
            category: document.getElementById('work-category').value.trim(),
            project_url: document.getElementById('work-route').value.trim() || 'case-studies.html',
            display_order: parseInt(document.getElementById('work-order').value) || 0,
            status: document.getElementById('work-status').value,
            image_url: imgUrl,
            image_alt: document.getElementById('work-image-alt').value.trim(),
            description: document.getElementById('work-desc').value.trim(),
            storage_provider: isCloudinary ? 'cloudinary' : 'local'
        };

        const isEdit = Boolean(id);
        const url = isEdit ? `/api/admin/work/${id}` : '/api/admin/work';
        const method = isEdit ? 'PUT' : 'POST';

        try {
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.closeModal('work-modal');
                this.showToast(data.message || (isEdit ? 'Work item updated and synced to website.' : 'Work item created and synced to website.'), 'success');
                await this.loadWorkItems();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Failed to save work item.', 'error');
            }
        } catch (err) {
            this.showToast('Server communication error.', 'error');
        }
    },

    async togglePublishWork(id, currentStatus) {
        const action = currentStatus === 'published' ? 'unpublish' : 'publish';
        try {
            const res = await fetch(`/api/admin/work/${id}/${action}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                await this.loadWorkItems();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Action failed.', 'error');
            }
        } catch (e) {
            this.showToast('Server error.', 'error');
        }
    },

    async deleteWorkItem(id) {
        if (!confirm('Are you sure you want to permanently delete this portfolio work item? It will be removed immediately from index.html and case-studies.html.')) return;
        try {
            const res = await fetch(`/api/admin/work/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                await this.loadWorkItems();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Could not delete work item.', 'error');
            }
        } catch (e) {
            this.showToast('Server error while deleting work item.', 'error');
        }
    },

    // ----------------- HOMEPAGE IMAGES -----------------
    async loadHomepageImages() {
        const grid = document.getElementById('homepage-images-grid');
        grid.innerHTML = '<div class="py-4 text-center"><i class="fa-regular fa-spinner fa-spin"></i> Loading image slots...</div>';

        try {
            const res = await fetch('/api/admin/homepage-images');
            const data = await res.json();
            this.allImages = data.images || [];

            grid.innerHTML = this.allImages.map(img => {
                const draftSrc = img.draft_src || img.current_src;
                const draftAlt = img.draft_alt || img.current_alt;
                const hasDraft = img.has_draft ? '<span class="badge badge-warning">Unpublished Draft</span>' : '<span class="badge badge-success">Live on Website</span>';

                return `
                <div class="image-slot-card">
                    <div class="image-slot-preview">
                        <img src="${this.formatImageUrl(draftSrc)}" alt="${this.escapeHtml(draftAlt)}">
                    </div>
                    <div class="image-slot-body">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                            <h4 class="image-slot-title">${this.escapeHtml(img.label)}</h4>
                            ${hasDraft}
                        </div>
                        <div class="image-slot-meta">
                            <span><i class="fa-regular fa-vector-polygon"></i> Slot Specs: ${img.recommended_dims || 'Fixed container'}</span>
                        </div>
                        <div class="image-slot-alt">
                            <strong>Alt:</strong> ${this.escapeHtml(draftAlt)}
                        </div>
                        <button class="btn btn-outline btn-block btn-sm" onclick="app.showReplaceImageModal('${img.slot_key}')">
                            <i class="fa-regular fa-camera-rotate"></i> Replace Image &amp; Alt
                        </button>
                    </div>
                </div>
                `;
            }).join('');
        } catch (e) {
            grid.innerHTML = '<div class="text-danger py-4">Failed to load homepage image slots.</div>';
        }
    },

    showReplaceImageModal(slotKey) {
        const slot = this.allImages.find(i => i.slot_key === slotKey);
        if (!slot) return;

        document.getElementById('replace-slot-key').value = slotKey;
        const curSrc = slot.draft_src || slot.current_src || '';
        const curAlt = slot.draft_alt || slot.current_alt || '';

        const urlInput = document.getElementById('replace-image-url');
        if (urlInput) urlInput.value = curSrc;

        const preview = document.getElementById('modal-img-preview');
        if (preview) {
            preview.src = this.formatImageUrl(curSrc);
            preview.removeAttribute('data-uploaded-path');
        }

        document.getElementById('replace-alt-text').value = curAlt;
        document.getElementById('modal-img-specs').textContent = `Slot Specs: ${slot.recommended_dims || 'Auto-fit cover'}`;
        const fileIn = document.getElementById('replace-file-input');
        if (fileIn) fileIn.value = '';

        this.openModal('image-replace-modal');
    },

    updateReplaceModalPreview(val) {
        const preview = document.getElementById('modal-img-preview');
        if (preview) {
            preview.removeAttribute('data-uploaded-path');
            preview.src = this.formatImageUrl(val);
        }
    },

    openMediaPickerForSlot() {
        this.openUniversalMediaPicker({
            title: 'Choose Homepage Slot Image',
            targetInputId: 'replace-image-url',
            targetAltId: 'replace-alt-text',
            onSelect: (url) => {
                this.updateReplaceModalPreview(url);
            }
        });
    },

    async handleImageFileSelect(input) {
        if (!input.files || input.files.length === 0) return;
        const file = input.files[0];

        // File validation
        if (file.size > 10 * 1024 * 1024) {
            this.showToast('File exceeds 10MB limit.', 'error');
            input.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', 'homepage');

        this.showToast('Uploading replacement image...', 'info');
        try {
            const res = await fetch('/api/admin/media/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const newPath = data.asset.secure_url || data.asset.file_path;
                const formatted = this.formatImageUrl(newPath);
                const preview = document.getElementById('modal-img-preview');
                if (preview) {
                    preview.src = formatted;
                    preview.setAttribute('data-uploaded-path', newPath);
                }
                const urlIn = document.getElementById('replace-image-url');
                if (urlIn) urlIn.value = newPath;
                this.showToast('Image uploaded. Click "Save Draft Replacement" to apply.', 'success');
            } else {
                this.showToast(data.detail || 'Upload failed.', 'error');
            }
        } catch (e) {
            this.showToast('Server error during upload.', 'error');
        }
    },

    async saveImageDraft() {
        const slotKey = document.getElementById('replace-slot-key').value;
        const preview = document.getElementById('modal-img-preview');
        const uploadedPath = preview ? preview.getAttribute('data-uploaded-path') : null;
        const urlInput = document.getElementById('replace-image-url');
        const enteredUrl = urlInput ? urlInput.value.trim() : '';
        const altText = document.getElementById('replace-alt-text').value.trim();

        const slot = this.allImages.find(i => i.slot_key === slotKey);
        let newSrc = uploadedPath || enteredUrl || (slot ? (slot.draft_src || slot.current_src) : '');

        if (newSrc.startsWith('res.cloudinary.com')) {
            newSrc = `https://${newSrc}`;
        }

        try {
            const res = await fetch(`/api/admin/homepage-images/${slotKey}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ draft_src: newSrc, draft_alt: altText })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.closeModal('image-replace-modal');
                this.showToast('Draft image updated. Click "Publish Images to Website" to make it live.', 'success');
                this.loadHomepageImages();
            } else {
                this.showToast(data.detail || 'Failed to save draft image.', 'error');
            }
        } catch (e) {
            this.showToast('Failed to save draft image.', 'error');
        }
    },

    async publishHomepageImages() {
        if (!confirm('Publish all draft images to the live homepage?')) return;
        try {
            const res = await fetch('/api/admin/homepage-images/publish', { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast('Homepage images published live successfully.', 'success');
                this.loadHomepageImages();
            }
        } catch (e) {
            this.showToast('Server error while publishing images.', 'error');
        }
    },

    // ----------------- PAGES CONTENT -----------------
    async loadPagesList() {
        const container = document.getElementById('pages-list-container');
        try {
            const res = await fetch('/api/admin/pages');
            const data = await res.json();
            this.pagesList = data.pages || [];

            container.innerHTML = this.pagesList.map(p => `
                <div class="list-group-item ${this.selectedPageKey === p.page_key ? 'active' : ''}" onclick="app.selectPage('${p.page_key}')">
                    <div>
                        <div>${this.escapeHtml(p.title)}</div>
                        <small class="text-muted">${p.file_name}</small>
                    </div>
                    ${p.has_draft ? '<span class="badge badge-warning">Draft</span>' : ''}
                </div>
            `).join('');

            if (!this.selectedPageKey && this.pagesList.length > 0) {
                this.selectPage(this.pagesList[0].page_key);
            }
        } catch (e) {
            container.innerHTML = '<div class="p-3 text-danger">Failed to load pages.</div>';
        }
    },

    async selectPage(pageKey) {
        this.selectedPageKey = pageKey;
        this.loadPagesList();

        const formContainer = document.getElementById('page-fields-form-container');
        formContainer.innerHTML = '<div class="py-5 text-center"><i class="fa-regular fa-spinner fa-spin"></i> Loading page fields...</div>';

        try {
            const res = await fetch(`/api/admin/pages/${pageKey}`);
            const data = await res.json();
            this.selectedPageData = data.page;

            document.getElementById('current-page-name').textContent = data.page.title;
            document.getElementById('current-page-file').textContent = `Source Template: ${data.page.file_name}`;
            document.getElementById('page-editor-actions').style.display = 'flex';

            const fields = data.page.fields;
            let html = `
                <div class="card mb-3" style="background: #F8FAFC; border: 1px solid #E2E8F0; padding: 16px; border-radius: 8px;">
                    <h4 style="font-size: 14px; margin-bottom: 12px; color: #081836;"><i class="fa-regular fa-magnifying-glass"></i> SEO &amp; Meta Settings</h4>
                    <div class="form-group">
                        <label>Page Title Tag (&lt;title&gt;)</label>
                        <input type="text" id="meta-title-input" value="${this.escapeHtml(data.page.meta_title || '')}">
                    </div>
                    <div class="form-group">
                        <label>Meta Description</label>
                        <textarea id="meta-desc-input" rows="2">${this.escapeHtml(data.page.meta_description || '')}</textarea>
                    </div>
                </div>
            `;

            // Group fields by section
            const sections = {};
            for (const [k, fld] of Object.entries(fields)) {
                const sec = fld.section || 'General Content';
                if (!sections[sec]) sections[sec] = [];
                sections[sec].push({ key: k, ...fld });
            }

            for (const [secName, fldList] of Object.entries(sections)) {
                html += `
                <div class="mb-4">
                    <h4 style="font-size: 14px; color: #1363DF; border-bottom: 2px solid #D8E5F8; padding-bottom: 6px; margin-bottom: 16px;">
                        <i class="fa-regular fa-layer-group"></i> ${this.escapeHtml(secName)}
                    </h4>
                `;
                fldList.forEach(f => {
                    const val = f.draft_value !== undefined ? f.draft_value : f.current_value;
                    if (f.type === 'textarea') {
                        html += `
                        <div class="form-group">
                            <label for="fld-${f.key}">${this.escapeHtml(f.label)}</label>
                            <textarea id="fld-${f.key}" data-field-key="${f.key}" rows="3">${this.escapeHtml(val)}</textarea>
                        </div>
                        `;
                    } else {
                        html += `
                        <div class="form-group">
                            <label for="fld-${f.key}">${this.escapeHtml(f.label)}</label>
                            <input type="text" id="fld-${f.key}" data-field-key="${f.key}" value="${this.escapeHtml(val)}">
                        </div>
                        `;
                    }
                });
                html += `</div>`;
            }

            formContainer.innerHTML = html;
        } catch (e) {
            formContainer.innerHTML = '<div class="text-danger py-4">Failed to load page fields.</div>';
        }
    },

    async savePageDraft() {
        if (!this.selectedPageKey) return;
        const inputs = document.querySelectorAll('[data-field-key]');
        const fields = {};
        inputs.forEach(input => {
            fields[input.getAttribute('data-field-key')] = input.value;
        });

        const metaTitle = document.getElementById('meta-title-input') ? document.getElementById('meta-title-input').value : null;
        const metaDesc = document.getElementById('meta-desc-input') ? document.getElementById('meta-desc-input').value : null;

        try {
            const res = await fetch(`/api/admin/pages/${this.selectedPageKey}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ fields, meta_title: metaTitle, meta_description: metaDesc })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast('Draft saved successfully.', 'success');
                this.loadPagesList();
            } else {
                this.showToast(data.detail || 'Failed to save draft.', 'error');
            }
        } catch (e) {
            this.showToast('Server error while saving draft.', 'error');
        }
    },

    async publishCurrentPage() {
        if (!this.selectedPageKey) return;
        // Auto-save draft before publishing
        await this.savePageDraft();

        if (!confirm(`Publish all edits for page '${this.selectedPageKey}' to the live website?`)) return;

        try {
            const res = await fetch(`/api/admin/pages/${this.selectedPageKey}/publish`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                this.selectPage(this.selectedPageKey);
            } else {
                this.showToast(data.detail || 'Publishing failed.', 'error');
            }
        } catch (e) {
            this.showToast('Server error during publish.', 'error');
        }
    },

    previewCurrentPage() {
        if (!this.selectedPageData) return;
        window.open(`/${this.selectedPageData.file_name}`, '_blank');
    },

    // ----------------- BLOG POSTS -----------------
    async loadBlogPosts(filter = 'all') {
        const tbody = document.getElementById('blog-table-body');
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><i class="fa-regular fa-spinner fa-spin"></i> Loading blog posts...</td></tr>';

        try {
            const res = await fetch(`/api/admin/blog?status=${filter}`);
            const data = await res.json();
            this.allPosts = data.posts || [];

            if (this.allPosts.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No blog posts found.</td></tr>';
                return;
            }

            tbody.innerHTML = this.allPosts.map(post => {
                const statusBadges = {
                    published: '<span class="badge badge-success">Published</span>',
                    draft: '<span class="badge badge-warning">Draft</span>',
                    archived: '<span class="badge badge-muted">Archived</span>'
                };
                return `
                <tr>
                    <td style="width: 70px;">
                        <img src="${this.formatImageUrl(post.featured_image)}" alt="thumb" style="width: 60px; height: 42px; object-fit: cover; border-radius: 4px;">
                    </td>
                    <td>
                        <strong style="color: #081836;">${this.escapeHtml(post.title)}</strong>
                        <div style="font-size: 11px; color: #64748B;">Slug: /${post.slug}</div>
                    </td>
                    <td>
                        <span class="badge badge-accent">${this.escapeHtml(post.category)}</span>
                        <div style="font-size: 11px; color: #64748B;">${this.escapeHtml(post.author)}</div>
                    </td>
                    <td>${post.published_date}</td>
                    <td>${statusBadges[post.status] || post.status}</td>
                    <td>
                        <div style="display: flex; gap: 6px;">
                            ${post.status !== 'published' ?
                                `<button class="btn btn-outline btn-sm" onclick="app.publishBlogPost(${post.id})"><i class="fa-regular fa-upload text-success"></i></button>` :
                                `<button class="btn btn-outline btn-sm" onclick="app.unpublishBlogPost(${post.id})"><i class="fa-regular fa-eye-slash"></i></button>`
                            }
                            <button class="btn btn-outline btn-sm" onclick="app.showEditBlogModal(${post.id})"><i class="fa-regular fa-pen"></i></button>
                            <button class="btn btn-danger btn-sm" onclick="app.deleteBlogPost(${post.id})"><i class="fa-regular fa-trash"></i></button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Failed to load blog posts.</td></tr>';
        }
    },

    filterBlog(status) {
        document.querySelectorAll('[data-blog-filter]').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-blog-filter') === status);
        });
        this.loadBlogPosts(status);
    },

    updateBlogImagePreview(val) {
        const prevImg = document.getElementById('blog-prev-img');
        if (prevImg) {
            prevImg.src = this.formatImageUrl(val || 'assets/images/blog/01.webp');
        }
    },

    openMediaPickerForBlog() {
        this.openUniversalMediaPicker({
            title: 'Choose Blog Post Featured Image',
            targetInputId: 'blog-image',
            targetAltId: 'blog-image-alt',
            onSelect: (url) => this.updateBlogImagePreview(url)
        });
    },

    pickBlogFeaturedImage() {
        this.openMediaPickerForBlog();
    },

    insertBlogTag(tag) {
        const ta = document.getElementById('blog-body');
        if (!ta) return;
        const start = ta.selectionStart || 0;
        const end = ta.selectionEnd || 0;
        const selected = ta.value.substring(start, end) || (tag === 'ul' ? 'List item' : 'Text here');
        let snippet = '';
        if (tag === 'ul') {
            snippet = `\n<ul>\n  <li>${selected}</li>\n</ul>\n`;
        } else if (tag === 'a') {
            snippet = `<a href="https://" target="_blank">${selected}</a>`;
        } else {
            snippet = `<${tag}>${selected}</${tag}>`;
        }
        ta.value = ta.value.substring(0, start) + snippet + ta.value.substring(end);
        ta.focus();
    },

    showAddBlogModal() {
        document.getElementById('blog-modal-title').textContent = 'Write New Blog Post';
        document.getElementById('blog-form').reset();
        document.getElementById('blog-id').value = '';
        document.getElementById('blog-author').value = 'Codozent Engineering Team';
        document.getElementById('blog-author-role').value = 'Software Architecture';
        document.getElementById('blog-image').value = 'assets/images/blog/01.webp';
        document.getElementById('blog-published-date').value = new Date().toISOString().slice(0, 10);
        document.getElementById('blog-status').value = 'published';
        this.updateBlogImagePreview('assets/images/blog/01.webp');
        this.openModal('blog-modal');
    },

    autoGenerateSlug(title) {
        if (!document.getElementById('blog-id').value) {
            const slug = title.toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/(^-|-$)+/g, '');
            document.getElementById('blog-slug').value = slug;
        }
    },

    async showEditBlogModal(postId) {
        try {
            const res = await fetch(`/api/admin/blog/${postId}`);
            const data = await res.json();
            const p = data.post;

            document.getElementById('blog-modal-title').textContent = 'Edit Blog Post';
            document.getElementById('blog-id').value = p.id;
            document.getElementById('blog-title').value = p.title;
            document.getElementById('blog-slug').value = p.slug;
            document.getElementById('blog-category').value = p.category;
            document.getElementById('blog-author').value = p.author;
            document.getElementById('blog-author-role').value = p.author_role || '';
            document.getElementById('blog-tags').value = p.tags || '';
            document.getElementById('blog-published-date').value = (p.published_date || '').slice(0, 10);
            document.getElementById('blog-image').value = p.featured_image;
            document.getElementById('blog-image-alt').value = p.featured_image_alt;
            document.getElementById('blog-excerpt').value = p.excerpt;
            document.getElementById('blog-body').value = p.body;
            document.getElementById('blog-status').value = p.status;
            this.updateBlogImagePreview(p.featured_image);

            this.openModal('blog-modal');
        } catch (e) {
            this.showToast('Failed to load article.', 'error');
        }
    },

    async handleBlogSubmit(e) {
        e.preventDefault();
        const id = document.getElementById('blog-id').value;
        let featImg = document.getElementById('blog-image').value.trim();
        if (featImg.startsWith('res.cloudinary.com')) {
            featImg = `https://${featImg}`;
        }
        const payload = {
            title: document.getElementById('blog-title').value.trim(),
            slug: document.getElementById('blog-slug').value.trim(),
            category: document.getElementById('blog-category').value.trim(),
            author: document.getElementById('blog-author').value.trim(),
            author_role: document.getElementById('blog-author-role').value.trim(),
            tags: document.getElementById('blog-tags').value.trim(),
            published_date: document.getElementById('blog-published-date').value || new Date().toISOString().slice(0, 10),
            featured_image: featImg,
            featured_image_alt: document.getElementById('blog-image-alt').value.trim(),
            excerpt: document.getElementById('blog-excerpt').value.trim(),
            body: document.getElementById('blog-body').value.trim(),
            status: document.getElementById('blog-status').value
        };

        const submitBtn = document.getElementById('blog-submit-btn');
        submitBtn.disabled = true;

        try {
            const endpoint = id ? `/api/admin/blog/${id}` : '/api/admin/blog';
            const method = id ? 'PUT' : 'POST';

            const res = await fetch(endpoint, {
                method,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (res.ok && data.success) {
                this.closeModal('blog-modal');
                this.showToast(data.message, 'success');
                this.loadBlogPosts();
                this.loadDashboardData();
            } else {
                this.showToast(data.detail || 'Could not save article.', 'error');
            }
        } catch (e) {
            this.showToast('Server error during article save.', 'error');
        } finally {
            submitBtn.disabled = false;
        }
    },

    async publishBlogPost(id) {
        try {
            const res = await fetch(`/api/admin/blog/${id}/publish`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                this.loadBlogPosts();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while publishing post.', 'error');
        }
    },

    async unpublishBlogPost(id) {
        try {
            const res = await fetch(`/api/admin/blog/${id}/unpublish`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'info');
                this.loadBlogPosts();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while unpublishing post.', 'error');
        }
    },

    async deleteBlogPost(id) {
        if (!confirm('Are you sure you want to delete this article permanently?')) return;
        try {
            const res = await fetch(`/api/admin/blog/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                this.loadBlogPosts();
                this.loadDashboardData();
            }
        } catch (e) {
            this.showToast('Server error while deleting article.', 'error');
        }
    },

    // ----------------- MEDIA LIBRARY (CLOUDINARY INTEGRATED) -----------------
    async loadMediaLibrary() {
        const grid = document.getElementById('media-library-grid');
        grid.innerHTML = '<div class="py-4 text-center"><i class="fa-regular fa-spinner fa-spin"></i> Loading assets...</div>';

        try {
            const res = await fetch('/api/admin/media');
            const data = await res.json();
            this.allMedia = data.media || [];

            // Update Cloudinary banner
            const banner = document.getElementById('cloudinary-status-banner');
            const bannerText = document.getElementById('cloudinary-status-text');
            const bannerBadge = document.getElementById('cloudinary-status-badge');
            if (data.cloudinary_configured) {
                if (banner) {
                    banner.style.background = '#ECFDF5';
                    banner.style.borderColor = '#A7F3D0';
                    banner.style.color = '#065F46';
                }
                if (bannerText) bannerText.innerHTML = '<strong>Cloudinary Active:</strong> Media assets are securely stored, managed, and globally delivered via Cloudinary with on-the-fly aspect-ratio preservation.';
                if (bannerBadge) {
                    bannerBadge.className = 'badge badge-success';
                    bannerBadge.textContent = 'Active (Cloudinary)';
                }
            } else {
                if (banner) {
                    banner.style.background = '#FFFBEB';
                    banner.style.borderColor = '#FDE68A';
                    banner.style.color = '#92400E';
                }
                if (bannerText) bannerText.innerHTML = '<strong>Cloudinary Standby (Local Fallback Active):</strong> CLOUDINARY_* environment variables are not yet set. Media is safely stored locally in assets/images/uploads/. Set credentials in .env to activate Cloudinary storage.';
                if (bannerBadge) {
                    bannerBadge.className = 'badge badge-warning';
                    bannerBadge.textContent = 'Local Fallback';
                }
            }

            this.renderMediaGrid(this.allMedia);
        } catch (e) {
            grid.innerHTML = '<div class="text-danger py-4">Failed to load media library.</div>';
        }
    },

    filterMedia(searchTerm) {
        const term = (searchTerm || '').toLowerCase().trim();
        if (!term) {
            this.renderMediaGrid(this.allMedia);
            return;
        }
        const filtered = (this.allMedia || []).filter(m => {
            const name = (m.filename || '').toLowerCase();
            const alt = (m.alt_text || '').toLowerCase();
            const folder = (m.folder || '').toLowerCase();
            const provider = (m.storage_provider || '').toLowerCase();
            return name.includes(term) || alt.includes(term) || folder.includes(term) || provider.includes(term);
        });
        this.renderMediaGrid(filtered);
    },

    renderMediaGrid(mediaList) {
        const grid = document.getElementById('media-library-grid');
        if (!grid) return;

        if (!mediaList || mediaList.length === 0) {
            grid.innerHTML = '<div class="py-4 text-muted col-span-full text-center">No uploaded media files matching criteria. Click "Upload Image" above to upload an asset.</div>';
            return;
        }

        grid.innerHTML = mediaList.map(m => {
            const isCloudinary = m.storage_provider === 'cloudinary';
            const displayUrl = this.formatImageUrl(m.secure_url || m.file_path);
            const copyUrl = m.secure_url || this.formatImageUrl(m.file_path);
            const sizeKb = m.file_size ? (m.file_size / 1024).toFixed(1) : '—';
            const dimStr = (m.width && m.height) ? `${m.width}×${m.height}` : '';
            const providerTag = isCloudinary ?
                '<span class="badge badge-purple" style="font-size:10px;"><i class="fa-regular fa-cloud"></i> Cloudinary</span>' :
                '<span class="badge badge-muted" style="font-size:10px;">Local</span>';

            return `
            <div class="media-asset-card">
                <div class="media-thumbnail">
                    <img src="${displayUrl}" alt="${this.escapeHtml(m.alt_text || m.filename)}">
                </div>
                <div class="media-info">
                    <div class="media-name" title="${this.escapeHtml(m.filename)}">${this.escapeHtml(m.filename)}</div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
                        <span style="color: #64748B; font-size: 11px;">${sizeKb} KB ${dimStr ? `• ${dimStr}` : ''}</span>
                        ${providerTag}
                    </div>
                    ${m.folder ? `<div style="font-size: 11px; color: #1363DF; margin-top: 2px;">📁 ${this.escapeHtml(m.folder)}</div>` : ''}
                    <div style="display: flex; gap: 4px; margin-top: 8px;">
                        <button class="btn btn-outline btn-sm" title="Copy URL" onclick="navigator.clipboard.writeText('${copyUrl}'); app.showToast('Asset URL copied to clipboard: ${this.escapeHtml(copyUrl)}', 'info');">
                            <i class="fa-regular fa-copy"></i> Copy URL
                        </button>
                        <button class="btn btn-danger btn-sm" title="Delete Asset" onclick="app.deleteMediaAsset(${m.id})">
                            <i class="fa-regular fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            `;
        }).join('');
    },

    showAddCloudinaryUrlModal() {
        document.getElementById('cloud-media-url').value = '';
        document.getElementById('cloud-media-alt').value = '';
        const prevImg = document.getElementById('cloud-media-prev-img');
        if (prevImg) prevImg.src = '';
        this.openModal('modal-add-cloudinary-url');
    },

    updateCloudMediaPreview(val) {
        const prevImg = document.getElementById('cloud-media-prev-img');
        if (prevImg) {
            prevImg.src = this.formatImageUrl(val);
        }
    },

    async handleAddCloudinaryUrl(e) {
        e.preventDefault();
        const rawUrl = document.getElementById('cloud-media-url').value.trim();
        const folder = document.getElementById('cloud-media-folder').value;
        const altText = document.getElementById('cloud-media-alt').value.trim();
        if (!rawUrl) {
            this.showToast('Please enter a valid Cloudinary image URL.', 'error');
            return;
        }

        const cleanUrl = this.formatImageUrl(rawUrl);
        const btn = document.getElementById('btn-save-cloud-url');
        if (btn) btn.disabled = true;

        try {
            const res = await fetch('/api/admin/media/add-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: cleanUrl,
                    folder: folder,
                    alt_text: altText,
                    category: folder.replace('codozent/', '')
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.closeModal('modal-add-cloudinary-url');
                this.showToast('Cloudinary asset successfully registered in Media Library!', 'success');
                this.loadMediaLibrary();
            } else {
                this.showToast(data.detail || 'Failed to add Cloudinary URL.', 'error');
            }
        } catch (err) {
            this.showToast('Server error while adding Cloudinary URL.', 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    },

    async openUniversalMediaPicker(options = {}) {
        this.currentPickerOptions = options;
        const modal = document.getElementById('modal-universal-media-picker');
        const grid = document.getElementById('universal-media-picker-grid');
        const titleEl = document.getElementById('universal-media-picker-title');
        if (!modal || !grid) return;

        if (titleEl && options.title) {
            titleEl.textContent = options.title;
        }
        modal.style.display = 'flex';
        grid.innerHTML = '<div class="col-span-full py-4 text-center text-muted"><i class="fa-regular fa-spinner fa-spin mr-1"></i> Loading media library...</div>';

        try {
            const res = await fetch('/api/admin/media');
            const data = await res.json();
            const items = (data.success && data.media) ? data.media : [];

            if (items.length === 0) {
                grid.innerHTML = '<div class="col-span-full py-4 text-center text-muted">No media assets found in library. Click "Add Cloudinary URL" to add image links.</div>';
                return;
            }

            grid.innerHTML = items.map(m => {
                const src = m.secure_url || m.file_path;
                const safeSrc = this.formatImageUrl(src);
                const title = m.filename || 'Image Asset';
                const alt = (m.alt_text || title).replace(/"/g, '&quot;');
                const escapedSrc = safeSrc.replace(/"/g, '&quot;');
                return `
                    <div class="media-picker-card" onclick="app.selectUniversalMedia('${escapedSrc}', '${alt}')" title="Click to select this image">
                        <img src="${safeSrc}" alt="${alt}" loading="lazy" />
                        <div class="media-title">${this.escapeHtml(title)}</div>
                    </div>
                `;
            }).join('');
        } catch (e) {
            grid.innerHTML = '<div class="col-span-full py-4 text-center text-danger">Failed to load media assets.</div>';
        }
    },

    selectUniversalMedia(url, alt) {
        const opts = this.currentPickerOptions || {};
        if (opts.targetInputId) {
            const input = document.getElementById(opts.targetInputId);
            if (input) input.value = url;
        }
        if (opts.targetAltId && alt && alt !== 'Image Asset') {
            const altInput = document.getElementById(opts.targetAltId);
            if (altInput && !altInput.value.trim()) altInput.value = alt;
        }
        if (typeof opts.onSelect === 'function') {
            opts.onSelect(url, alt);
        }
        this.closeUniversalMediaPicker();
        this.showToast('Image selected from Media Library.', 'info');
    },

    closeUniversalMediaPicker() {
        const modal = document.getElementById('modal-universal-media-picker');
        if (modal) modal.style.display = 'none';
        this.currentPickerOptions = null;
    },

    async handleMediaUpload(input) {
        if (!input.files || input.files.length === 0) return;
        const file = input.files[0];
        const folder = document.getElementById('media-folder-select')?.value || 'codozent/general';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('folder', folder);

        this.showToast(`Uploading asset to ${folder}...`, 'info');
        try {
            const res = await fetch('/api/admin/media/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'Asset uploaded successfully.', 'success');
                this.loadMediaLibrary();
            } else {
                this.showToast(data.detail || 'Upload failed.', 'error');
            }
        } catch (e) {
            this.showToast('Server error during upload.', 'error');
        } finally {
            input.value = '';
        }
    },

    async deleteMediaAsset(assetId) {
        if (!confirm('Are you sure you want to delete this media asset? This action cannot be undone.')) return;
        try {
            const res = await fetch(`/api/admin/media/${assetId}`, { method: 'DELETE' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'Asset deleted successfully.', 'success');
                this.loadMediaLibrary();
            } else {
                this.showToast(data.detail || 'Could not delete asset.', 'error');
            }
        } catch (e) {
            this.showToast('Server error while deleting asset.', 'error');
        }
    },

    // ----------------- ACCOUNT SETTINGS -----------------
    async handleChangePassword(e) {
        e.preventDefault();
        const current_password = document.getElementById('current-pass').value;
        const new_password = document.getElementById('new-pass').value;
        const confirm_pass = document.getElementById('confirm-pass').value;

        if (new_password !== confirm_pass) {
            this.showToast('New passwords do not match.', 'error');
            return;
        }

        try {
            const res = await fetch('/api/auth/change-password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ current_password, new_password })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message, 'success');
                document.getElementById('change-password-form').reset();
            } else {
                this.showToast(data.detail || 'Password change failed.', 'error');
            }
        } catch (e) {
            this.showToast('Server error while updating password.', 'error');
        }
    },

    // ----------------- USER MANAGEMENT (ADMIN ONLY) -----------------
    async loadUsers() {
        const tbody = document.getElementById('users-table-body');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><i class="fa-regular fa-spinner fa-spin"></i> Loading users...</td></tr>';

        try {
            const res = await fetch('/api/admin/users');
            if (!res.ok) {
                if (res.status === 404 || res.status === 403) {
                    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Access Denied: Administrative privileges required.</td></tr>';
                    return;
                }
                throw new Error('Failed to load users');
            }
            const data = await res.json();
            this.allUsers = data.users || [];

            if (this.allUsers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No users found. Click "+ Add New User" to create one.</td></tr>';
                return;
            }

            tbody.innerHTML = this.allUsers.map(u => {
                const roleBadges = {
                    admin: '<span class="badge badge-purple"><i class="fa-regular fa-shield-check mr-2"></i> Admin</span>',
                    editor: '<span class="badge badge-primary"><i class="fa-regular fa-pen-to-square mr-2"></i> Editor</span>',
                    viewer: '<span class="badge badge-muted"><i class="fa-regular fa-eye mr-2"></i> Viewer</span>'
                };
                const statusBadges = {
                    active: '<span class="badge badge-success"><i class="fa-regular fa-check mr-2"></i> Active</span>',
                    disabled: '<span class="badge badge-danger"><i class="fa-regular fa-ban mr-2"></i> Disabled</span>'
                };

                const createdStr = u.created_at ? new Date(u.created_at).toLocaleDateString() : '—';
                const lastLoginStr = u.last_login ? new Date(u.last_login).toLocaleString() : '<span class="text-muted">Never</span>';
                const isSelf = this.currentUser && this.currentUser.id === u.id;

                return `
                <tr>
                    <td>
                        <strong style="color: #081836; font-size: 14px;">${this.escapeHtml(u.full_name || 'User')}</strong>
                        ${isSelf ? '<span class="badge badge-accent ml-2" style="font-size: 10px; margin-left: 6px;">You</span>' : ''}
                        <div style="font-size: 12px; color: #64748B;">${this.escapeHtml(u.email)}</div>
                    </td>
                    <td>${roleBadges[u.role] || `<span class="badge badge-muted">${u.role}</span>`}</td>
                    <td>${statusBadges[u.status] || `<span class="badge badge-muted">${u.status}</span>`}</td>
                    <td style="font-size: 12px; color: #64748B;">${createdStr}</td>
                    <td style="font-size: 12px; color: #64748B;">${lastLoginStr}</td>
                    <td class="text-right">
                        <div style="display: inline-flex; gap: 6px;">
                            <button class="btn btn-outline btn-sm" title="Edit User" onclick="app.showEditUserModal(${u.id})">
                                <i class="fa-regular fa-user-pen"></i> Edit
                            </button>
                            <button class="btn btn-outline btn-sm" title="Reset Password" onclick="app.showResetUserPasswordModal(${u.id})">
                                <i class="fa-regular fa-key"></i> Reset
                            </button>
                            <button class="btn btn-danger btn-sm" title="${isSelf ? 'Cannot delete own account' : 'Delete User'}"
                                onclick="app.deleteUser(${u.id}, '${this.escapeHtml(u.email)}', '${u.role}')"
                                ${isSelf ? 'disabled style="opacity: 0.4; cursor: not-allowed;"' : ''}>
                                <i class="fa-regular fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');
        } catch (err) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Server error while loading users list.</td></tr>';
        }
    },

    showAddUserModal() {
        const form = document.getElementById('user-add-form');
        if (form) form.reset();
        this.openModal('user-add-modal');
    },

    async handleAddUser(e) {
        e.preventDefault();
        const full_name = document.getElementById('user-add-name').value.trim();
        const email = document.getElementById('user-add-email').value.trim();
        const role = document.getElementById('user-add-role').value;
        const password = document.getElementById('user-add-pass').value;

        if (password.length < 8) {
            this.showToast('Password must be at least 8 characters long.', 'error');
            return;
        }

        const btn = document.getElementById('user-add-submit-btn');
        btn.disabled = true;
        btn.textContent = 'Creating User...';

        try {
            const res = await fetch('/api/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name, email, role, password })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'User created successfully.', 'success');
                this.closeModal('user-add-modal');
                this.loadUsers();
            } else {
                this.showToast(data.detail || 'Could not create user.', 'error');
            }
        } catch (err) {
            this.showToast('Server error while creating user.', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Create User';
        }
    },

    showEditUserModal(userId) {
        const u = (this.allUsers || []).find(item => item.id === userId);
        if (!u) return;

        document.getElementById('user-edit-id').value = u.id;
        document.getElementById('user-edit-email').value = u.email;
        document.getElementById('user-edit-name').value = u.full_name || '';
        document.getElementById('user-edit-role').value = u.role;
        document.getElementById('user-edit-status').value = u.status;

        this.openModal('user-edit-modal');
    },

    async handleEditUser(e) {
        e.preventDefault();
        const userId = document.getElementById('user-edit-id').value;
        const full_name = document.getElementById('user-edit-name').value.trim();
        const role = document.getElementById('user-edit-role').value;
        const status = document.getElementById('user-edit-status').value;

        const btn = document.getElementById('user-edit-submit-btn');
        btn.disabled = true;
        btn.textContent = 'Saving Changes...';

        try {
            const res = await fetch(`/api/admin/users/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name, role, status })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'User updated successfully.', 'success');
                this.closeModal('user-edit-modal');
                this.loadUsers();
            } else {
                this.showToast(data.detail || 'Could not update user.', 'error');
            }
        } catch (err) {
            this.showToast('Server error while updating user.', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Save Changes';
        }
    },

    showResetUserPasswordModal(userId) {
        const u = (this.allUsers || []).find(item => item.id === userId);
        if (!u) return;

        document.getElementById('user-reset-id').value = u.id;
        document.getElementById('user-reset-target-email').textContent = `${u.full_name || ''} (${u.email})`;
        document.getElementById('user-reset-new-pass').value = '';

        this.openModal('user-reset-pwd-modal');
    },

    async handleResetUserPassword(e) {
        e.preventDefault();
        const userId = document.getElementById('user-reset-id').value;
        const new_password = document.getElementById('user-reset-new-pass').value;

        if (new_password.length < 8) {
            this.showToast('Password must be at least 8 characters long.', 'error');
            return;
        }

        const btn = document.getElementById('user-reset-submit-btn');
        btn.disabled = true;
        btn.textContent = 'Resetting Password...';

        try {
            const res = await fetch(`/api/admin/users/${userId}/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'Password reset successfully.', 'success');
                this.closeModal('user-reset-pwd-modal');
            } else {
                this.showToast(data.detail || 'Could not reset password.', 'error');
            }
        } catch (err) {
            this.showToast('Server error while resetting password.', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Confirm Password Reset';
        }
    },

    async deleteUser(userId, email, role) {
        if (this.currentUser && this.currentUser.id === userId) {
            this.showToast('You cannot delete your own administrative account.', 'error');
            return;
        }

        const confirmed = confirm(`Are you sure you want to permanently delete user account '${email}'? This action cannot be undone.`);
        if (!confirmed) return;

        try {
            const res = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast(data.message || 'User deleted successfully.', 'success');
                this.loadUsers();
            } else {
                this.showToast(data.detail || 'Could not delete user.', 'error');
            }
        } catch (err) {
            this.showToast('Server error while deleting user.', 'error');
        }
    },

    generatePassword(targetInputId) {
        const length = 12;
        const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*";
        let pwd = "Cdz_";
        for (let i = 0; i < length; i++) {
            pwd += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        const input = document.getElementById(targetInputId);
        if (input) {
            input.value = pwd;
            input.type = 'text'; // Show generated password clearly
            input.focus();
            input.select();
            this.showToast('Generated secure temporary password: ' + pwd, 'info');
        }
    },

    // ----------------- UTILS & MODALS -----------------
    openModal(id) {
        document.getElementById(id).classList.add('active');
    },

    closeModal(id) {
        document.getElementById(id).classList.remove('active');
    },

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = {
            success: 'fa-regular fa-circle-check text-success',
            error: 'fa-regular fa-triangle-exclamation text-danger',
            info: 'fa-regular fa-circle-info'
        };
        toast.innerHTML = `<i class="${icons[type] || icons.info}"></i> <span>${this.escapeHtml(message)}</span>`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
};

window.addEventListener('DOMContentLoaded', () => {
    app.init();
});
