/**
 * Codozent All-in-One Cloudflare Edge Worker
 * Fully hosts the entire website, dynamic Edge SSR, and CMS backend on Cloudflare.
 * - 0ms cold starts (never goes to sleep)
 * - Connects directly to Supabase REST API
 * - Edge Server-Side Rendering via HTMLRewriter for instant SEO & live updates
 * - Complete CRUD Admin Authentication and CMS APIs
 * - All secrets and credentials read from Cloudflare Environment Variables / Build Env
 */

import buildEnv from './_env_generated.js';

// ----------------- ENVIRONMENT HELPER -----------------

function getEnvVar(env, key, defaultVal = '') {
    if (env && typeof env[key] !== 'undefined' && env[key] !== null && String(env[key]).trim() !== '') {
        return String(env[key]);
    }
    if (typeof buildEnv !== 'undefined' && buildEnv && typeof buildEnv[key] !== 'undefined' && buildEnv[key] !== null && String(buildEnv[key]).trim() !== '') {
        return String(buildEnv[key]);
    }
    try {
        if (typeof globalThis !== 'undefined' && typeof globalThis[key] !== 'undefined' && globalThis[key] !== null && String(globalThis[key]).trim() !== '') {
            return String(globalThis[key]);
        }
    } catch {}
    try {
        if (typeof process !== 'undefined' && process.env && typeof process.env[key] !== 'undefined' && process.env[key] !== null && String(process.env[key]).trim() !== '') {
            return String(process.env[key]);
        }
    } catch {}
    return defaultVal;
}

// ----------------- CRYPTO / JWT SESSION HELPERS -----------------

function base64UrlEncode(str) {
    const bytes = new TextEncoder().encode(str);
    let binary = '';
    bytes.forEach(b => binary += String.fromCharCode(b));
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(str) {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) str += '=';
    const binary = atob(str);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder().decode(bytes);
}

async function signJwt(payload, secret) {
    const header = { alg: 'HS256', typ: 'JWT' };
    const encHeader = base64UrlEncode(JSON.stringify(header));
    const encPayload = base64UrlEncode(JSON.stringify(payload));
    const data = `${encHeader}.${encPayload}`;

    const key = await crypto.subtle.importKey(
        'raw',
        new TextEncoder().encode(secret),
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign']
    );
    const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
    let binary = '';
    new Uint8Array(signature).forEach(b => binary += String.fromCharCode(b));
    const encSig = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return `${data}.${encSig}`;
}

async function verifyJwt(token, secret) {
    try {
        const parts = token.split('.');
        if (parts.length !== 3) return null;
        const [encHeader, encPayload, encSig] = parts;
        const data = `${encHeader}.${encPayload}`;

        const key = await crypto.subtle.importKey(
            'raw',
            new TextEncoder().encode(secret),
            { name: 'HMAC', hash: 'SHA-256' },
            false,
            ['verify']
        );

        let sigB64 = encSig.replace(/-/g, '+').replace(/_/g, '/');
        while (sigB64.length % 4) sigB64 += '=';
        const sigBin = atob(sigB64);
        const sigBytes = new Uint8Array(sigBin.length);
        for (let i = 0; i < sigBin.length; i++) sigBytes[i] = sigBin.charCodeAt(i);

        const isValid = await crypto.subtle.verify('HMAC', key, sigBytes, new TextEncoder().encode(data));
        if (!isValid) return null;

        const payload = JSON.parse(base64UrlDecode(encPayload));
        if (payload.exp && Date.now() / 1000 > payload.exp) return null;
        return payload;
    } catch {
        return null;
    }
}

function parseCookies(cookieHeader) {
    const list = {};
    if (!cookieHeader) return list;
    cookieHeader.split(';').forEach(cookie => {
        const [name, ...rest] = cookie.split('=');
        if (!name || !rest.length) return;
        list[name.trim()] = decodeURIComponent(rest.join('=').trim());
    });
    return list;
}

// ----------------- SUPABASE REST API CLIENT -----------------

async function querySupabaseRaw(env, path, options = {}) {
    let supabaseUrl = getEnvVar(env, 'SUPABASE_URL').trim();
    const supabaseKey = (
        getEnvVar(env, 'SUPABASE_KEY') ||
        getEnvVar(env, 'SUPABASE_SERVICE_ROLE_KEY') ||
        getEnvVar(env, 'SUPABASE_ANON_KEY')
    ).trim();

    if (!supabaseUrl || !supabaseKey) {
        return { ok: false, status: 0, error: 'Missing SUPABASE_URL or SUPABASE_KEY', data: null };
    }

    supabaseUrl = supabaseUrl.replace(/\/+$/, '');
    if (!supabaseUrl.startsWith('http://') && !supabaseUrl.startsWith('https://')) {
        return { ok: false, status: 0, error: 'SUPABASE_URL must start with https://', data: null };
    }

    const url = `${supabaseUrl}/rest/v1/${path}`;
    const headers = {
        'apikey': supabaseKey,
        'Authorization': `Bearer ${supabaseKey}`,
        'Content-Type': 'application/json',
        ...(options.headers || {})
    };

    if (options.prefer) {
        headers['Prefer'] = options.prefer;
    }

    try {
        const res = await fetch(url, {
            method: options.method || 'GET',
            headers,
            body: options.body !== undefined ? JSON.stringify(options.body) : undefined
        });

        if (!res.ok) {
            const errText = await res.text();
            return { ok: false, status: res.status, error: errText.slice(0, 300), data: null };
        }

        if (res.status === 204) {
            return { ok: true, status: 204, error: null, data: [] };
        }
        const text = await res.text();
        const parsed = text ? JSON.parse(text) : [];
        return { ok: true, status: res.status, error: null, data: parsed };
    } catch (e) {
        return { ok: false, status: 0, error: e.message || 'Network fetch failed', data: null };
    }
}

async function querySupabase(env, path, options = {}) {
    const res = await querySupabaseRaw(env, path, options);
    return res.ok ? res.data : null;
}

// ----------------- MAIN WORKER DISPATCHER -----------------

export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);
        const secretKey = getEnvVar(env, 'CMS_SECRET_KEY', 'insecure-placeholder-set-cms-secret-key-in-env');

        // 1. CORS Preflight
        if (request.method === 'OPTIONS') {
            return new Response(null, {
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                    'Access-Control-Allow-Credentials': 'true'
                }
            });
        }

        // 2. Health Check Route
        if (url.pathname === '/api/health' || url.pathname === '/health') {
            const rawUrl = getEnvVar(env, 'SUPABASE_URL').trim();
            const rawKey = (getEnvVar(env, 'SUPABASE_KEY') || getEnvVar(env, 'SUPABASE_SERVICE_ROLE_KEY') || getEnvVar(env, 'SUPABASE_ANON_KEY')).trim();
            const hasUrl = Boolean(rawUrl);
            const hasKey = Boolean(rawKey);
            const hasEmail = Boolean(getEnvVar(env, 'ADMIN_EMAIL').trim());
            const hasPass = Boolean(getEnvVar(env, 'ADMIN_PASSWORD').trim());

            let dbStatus = 'NOT_CONFIGURED';
            let dbError = null;
            let urlHost = null;
            try {
                if (rawUrl) urlHost = new URL(rawUrl).hostname;
            } catch {
                urlHost = 'INVALID_URL_FORMAT';
            }

            if (hasUrl && hasKey) {
                const probe = await querySupabaseRaw(env, 'homepage_video_section?select=id&limit=1');
                if (probe.ok) {
                    dbStatus = 'CONNECTED';
                } else {
                    dbStatus = `ERROR_CONNECTING_TO_SUPABASE (HTTP ${probe.status})`;
                    dbError = probe.error;
                }
            }

            return jsonResponse({
                status: (dbStatus === 'CONNECTED' && hasEmail && hasPass) ? 'healthy' : 'setup_required',
                service: 'Codozent Cloudflare Edge Worker',
                config: {
                    SUPABASE_URL: hasUrl ? `CONFIGURED (${urlHost})` : 'MISSING',
                    SUPABASE_KEY: hasKey ? `CONFIGURED (len=${rawKey.length}, prefix=${rawKey.slice(0, 6)}...)` : 'MISSING',
                    ADMIN_EMAIL: hasEmail ? 'CONFIGURED' : 'MISSING',
                    ADMIN_PASSWORD: hasPass ? 'CONFIGURED' : 'MISSING',
                    CMS_SECRET_KEY: getEnvVar(env, 'CMS_SECRET_KEY') ? 'CONFIGURED' : 'USING_DEFAULT_SALT'
                },
                database_status: dbStatus,
                database_error: dbError
            });
        }

        // 3. Auth Routes
        if (url.pathname === '/api/auth/login' && request.method === 'POST') {
            return handleLogin(request, env, secretKey);
        }
        if (url.pathname === '/api/auth/logout') {
            return handleLogout();
        }
        if (url.pathname === '/api/auth/me') {
            return handleAuthMe(request, secretKey);
        }
        if (url.pathname === '/api/auth/change-password' && request.method === 'POST') {
            return handlePasswordChange(request, env, secretKey);
        }

        // 4. Public API Routes
        if (url.pathname.startsWith('/api/public/')) {
            return handlePublicApi(url, env);
        }

        // 5. Admin API Routes (Protected)
        if (url.pathname.startsWith('/api/admin/')) {
            const session = await getSession(request, secretKey);
            if (!session) {
                return jsonResponse({ detail: 'Authentication required' }, 401);
            }
            return handleAdminApi(request, url, env, session);
        }

        // 6. Admin Panel UI Routes (Protected Server-Side)
        if (url.pathname === '/admin' || url.pathname === '/admin/') {
            const session = await getSession(request, secretKey);
            if (!session) {
                return Response.redirect(`${url.origin}/admin/login`, 302);
            }
            const adminReq = new Request(new URL('/admin/index.html', request.url), request);
            return env.ASSETS.fetch(adminReq);
        }

        if (url.pathname === '/admin/login' || url.pathname === '/admin/login/') {
            const session = await getSession(request, secretKey);
            if (session) {
                return Response.redirect(`${url.origin}/admin`, 302);
            }
            const loginReq = new Request(new URL('/admin/login.html', request.url), request);
            return env.ASSETS.fetch(loginReq);
        }

        // 7. Dynamic Edge SSR for Homepage (Live sync on load)
        if (url.pathname === '/' || url.pathname === '/index.html') {
            return handleHomepageSSR(request, env);
        }

        // 8. Dynamic Blog Details (blog-details.html?slug=...)
        if (url.pathname === '/blog-details.html' && url.searchParams.has('slug')) {
            return handleBlogDetailsSSR(request, env, url.searchParams.get('slug'));
        }

        // 9. Fallback: Serve static assets directly from Cloudflare Edge
        return env.ASSETS.fetch(request);
    }
};

// ----------------- AUTH HANDLERS -----------------

async function getSession(request, secretKey) {
    const cookies = parseCookies(request.headers.get('Cookie'));
    const token = cookies['codozent_session'] || cookies['admin_token'];
    if (!token) return null;
    return await verifyJwt(token, secretKey);
}

async function handleLogin(request, env, secretKey) {
    try {
        const body = await request.json();
        const email = (body.email || '').trim().toLowerCase();
        const password = body.password || '';

        const adminEmail = getEnvVar(env, 'ADMIN_EMAIL').trim().toLowerCase();
        const adminPass = getEnvVar(env, 'ADMIN_PASSWORD');

        if (!adminEmail || !adminPass) {
            return jsonResponse({
                detail: 'ADMIN_EMAIL or ADMIN_PASSWORD is not loaded in this deployment snapshot.'
            }, 500);
        }

        if (email === adminEmail && password === adminPass) {
            const token = await signJwt(
                { email, role: 'admin', exp: Math.floor(Date.now() / 1000) + (86400 * 7) },
                secretKey
            );
            const userObj = { email, role: 'admin', full_name: 'Administrator' };
            const headers = new Headers();
            headers.set('Content-Type', 'application/json');
            headers.append('Set-Cookie', `codozent_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800; Secure`);
            headers.append('Set-Cookie', `admin_token=${token}; Path=/; SameSite=Lax; Max-Age=604800; Secure`);
            return new Response(JSON.stringify({ success: true, message: 'Logged in successfully', user: userObj }), {
                headers
            });
        }

        return jsonResponse({ detail: 'Invalid email or password' }, 401);
    } catch {
        return jsonResponse({ detail: 'Invalid request format' }, 400);
    }
}

function handleLogout() {
    const headers = new Headers();
    headers.set('Content-Type', 'application/json');
    headers.append('Set-Cookie', 'codozent_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Secure');
    headers.append('Set-Cookie', 'admin_token=; Path=/; SameSite=Lax; Max-Age=0; Secure');
    return new Response(JSON.stringify({ success: true, message: 'Logged out' }), { headers });
}

async function handleAuthMe(request, secretKey) {
    const session = await getSession(request, secretKey);
    if (!session) {
        return jsonResponse({ authenticated: false, role: 'visitor' }, 401);
    }
    return jsonResponse({
        authenticated: true,
        user: { email: session.email, role: session.role || 'admin', full_name: 'Administrator' }
    });
}

async function handlePasswordChange(request, env, secretKey) {
    const session = await getSession(request, secretKey);
    if (!session) return jsonResponse({ detail: 'Authentication required' }, 401);
    return jsonResponse({
        success: true,
        message: 'To change your production admin password, update ADMIN_PASSWORD in Cloudflare Dashboard -> Settings -> Variables & Secrets.'
    });
}

// ----------------- PUBLIC API HANDLERS -----------------

async function handlePublicApi(url, env) {
    const path = url.pathname.replace('/api/public/', '').replace(/\/$/, '');

    if (path === 'video-section') {
        const rows = await querySupabase(env, 'homepage_video_section?id=eq.1&select=*');
        if (rows && rows.length > 0) {
            const row = rows[0];
            return jsonResponse({
                success: true,
                video_enabled: Boolean(row.video_enabled),
                video_url: row.video_url || 'https://www.youtube.com/watch?v=vZE0j_WCRvI',
                image_url: row.image_url || 'assets/images/video/01.webp',
                image_alt: row.image_alt || 'Engineering Process',
                title: row.title || '',
                description: row.description || ''
            });
        }
        return jsonResponse({
            success: true,
            video_enabled: false,
            video_url: 'https://www.youtube.com/watch?v=vZE0j_WCRvI',
            image_url: 'assets/images/video/01.webp',
            image_alt: 'Engineering Process'
        });
    }

    if (path === 'homepage-images') {
        const rows = await querySupabase(env, 'homepage_images?select=*&order=slot_key.asc');
        return jsonResponse({ success: true, images: rows || [] });
    }

    if (path === 'work') {
        const rows = await querySupabase(env, 'work_items?status=eq.published&order=display_order.asc,id.asc');
        return jsonResponse({ success: true, work: rows || [] });
    }

    if (path === 'jobs') {
        const rows = await querySupabase(env, 'jobs?status=eq.published&order=id.desc');
        return jsonResponse({ success: true, jobs: rows || [] });
    }

    if (path === 'blog') {
        const rows = await querySupabase(env, 'blog_posts?status=eq.published&order=published_date.desc,id.desc');
        return jsonResponse({ success: true, posts: rows || [] });
    }

    if (path.startsWith('blog/')) {
        const slug = decodeURIComponent(path.replace('blog/', ''));
        const rows = await querySupabase(env, `blog_posts?slug=eq.${encodeURIComponent(slug)}&status=eq.published&limit=1`);
        if (rows && rows.length > 0) {
            return jsonResponse({ success: true, post: rows[0] });
        }
        return jsonResponse({ detail: 'Article not found' }, 404);
    }

    if (path.startsWith('pages/')) {
        const pageKey = decodeURIComponent(path.replace('pages/', ''));
        const rows = await querySupabase(env, `pages?page_key=eq.${encodeURIComponent(pageKey)}&limit=1`);
        if (rows && rows.length > 0) {
            const page = rows[0];
            let fields = {};
            try { fields = JSON.parse(page.fields_json || '{}'); } catch {}
            return jsonResponse({ success: true, page: { ...page, fields } });
        }
        return jsonResponse({ detail: 'Page not found' }, 404);
    }

    return jsonResponse({ detail: 'Not found' }, 404);
}

// ----------------- ADMIN API HANDLERS -----------------

async function handleAdminApi(request, url, env, session) {
    const path = url.pathname.replace('/api/admin/', '').replace(/\/$/, '');
    const method = request.method;

    // 1. Stats
    if (path === 'stats') {
        const [jobs, work, blogs, images] = await Promise.all([
            querySupabase(env, 'jobs?select=id,status'),
            querySupabase(env, 'work_items?select=id,status'),
            querySupabase(env, 'blog_posts?select=id,status'),
            querySupabase(env, 'homepage_images?select=slot_key')
        ]);
        const j = jobs || [];
        const w = work || [];
        const b = blogs || [];
        const i = images || [];
        return jsonResponse({
            success: true,
            stats: {
                jobs_count: j.length,
                published_jobs: j.filter(x => x.status === 'published').length,
                work_count: w.length,
                published_work: w.filter(x => x.status === 'published').length,
                blog_count: b.length,
                published_blogs: b.filter(x => x.status === 'published').length,
                images_count: i.length
            }
        });
    }

    // 2. Video Section
    if (path === 'video-section') {
        if (method === 'GET') {
            const rows = await querySupabase(env, 'homepage_video_section?id=eq.1&select=*');
            const data = (rows && rows[0]) || { id: 1, video_enabled: 1, video_url: '', image_url: '', image_alt: '' };
            data.video_enabled = Boolean(data.video_enabled);
            return jsonResponse({ success: true, video_section: data });
        }
        if (method === 'POST' || method === 'PUT') {
            const body = await request.json();
            const now = new Date().toISOString();
            const payload = {
                video_enabled: body.video_enabled ? 1 : 0,
                video_url: (body.video_url || '').trim(),
                image_url: (body.image_url || '').trim(),
                image_alt: (body.image_alt || '').trim(),
                updated_at: now
            };
            const res = await querySupabaseRaw(env, 'homepage_video_section?id=eq.1', {
                method: 'PATCH',
                prefer: 'return=representation',
                body: payload
            });
            if (!res.ok) {
                return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            }
            if (payload.image_url) {
                await querySupabase(env, 'homepage_images?slot_key=eq.video_thumbnail', {
                    method: 'PATCH',
                    body: { current_src: payload.image_url, draft_src: payload.image_url, updated_at: now }
                });
            }
            return jsonResponse({ success: true, message: 'Video section updated successfully.', video_section: res.data?.[0] || payload });
        }
    }

    // 3. Homepage Images
    if (path === 'homepage-images') {
        const rows = await querySupabase(env, 'homepage_images?select=*&order=slot_key.asc');
        return jsonResponse({ success: true, images: rows || [] });
    }

    if (path === 'homepage-images/publish' && method === 'POST') {
        const rows = await querySupabase(env, 'homepage_images?select=*') || [];
        const now = new Date().toISOString();
        for (const slot of rows) {
            if (slot.has_draft || slot.draft_src || slot.draft_alt) {
                await querySupabase(env, `homepage_images?slot_key=eq.${encodeURIComponent(slot.slot_key)}`, {
                    method: 'PATCH',
                    body: {
                        current_src: slot.draft_src || slot.current_src,
                        current_alt: slot.draft_alt || slot.current_alt,
                        has_draft: 0,
                        updated_at: now
                    }
                });
            }
        }
        return jsonResponse({ success: true, message: 'All homepage images published live.' });
    }

    if (path.startsWith('homepage-images/') && method === 'PUT') {
        const slotKey = decodeURIComponent(path.replace('homepage-images/', ''));
        const body = await request.json();
        const payload = {
            draft_src: (body.draft_src || '').trim(),
            draft_alt: (body.draft_alt || '').trim(),
            has_draft: 1,
            updated_at: new Date().toISOString()
        };
        const res = await querySupabaseRaw(env, `homepage_images?slot_key=eq.${encodeURIComponent(slotKey)}`, {
            method: 'PATCH',
            prefer: 'return=representation',
            body: payload
        });
        if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        return jsonResponse({ success: true, message: 'Draft image saved.', image: res.data?.[0] || payload });
    }

    // 4. Pages (Page Content)
    if (path === 'pages') {
        const rows = await querySupabase(env, 'pages?select=*&order=page_key.asc') || [];
        const pages = rows.map(p => {
            let fields = {};
            try { fields = JSON.parse(p.fields_json || '{}'); } catch {}
            return { ...p, fields };
        });
        return jsonResponse({ success: true, pages });
    }

    if (path.startsWith('pages/') && path.endsWith('/publish') && method === 'POST') {
        const pageKey = decodeURIComponent(path.replace('pages/', '').replace('/publish', ''));
        const rows = await querySupabase(env, `pages?page_key=eq.${encodeURIComponent(pageKey)}&limit=1`);
        if (!rows || !rows[0]) return jsonResponse({ detail: 'Page not found' }, 404);
        const page = rows[0];
        let fields = {};
        try { fields = JSON.parse(page.fields_json || '{}'); } catch {}
        for (const k in fields) {
            if (fields[k] && typeof fields[k] === 'object') {
                fields[k].current_value = fields[k].draft_value ?? fields[k].current_value;
            }
        }
        const now = new Date().toISOString();
        const res = await querySupabaseRaw(env, `pages?page_key=eq.${encodeURIComponent(pageKey)}`, {
            method: 'PATCH',
            prefer: 'return=representation',
            body: {
                fields_json: JSON.stringify(fields),
                has_draft: 0,
                published_at: now,
                updated_at: now
            }
        });
        if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        return jsonResponse({ success: true, message: 'Page published live.' });
    }

    if (path.startsWith('pages/')) {
        const pageKey = decodeURIComponent(path.replace('pages/', ''));
        if (method === 'GET') {
            const rows = await querySupabase(env, `pages?page_key=eq.${encodeURIComponent(pageKey)}&limit=1`);
            if (!rows || !rows[0]) return jsonResponse({ detail: 'Page not found' }, 404);
            const page = rows[0];
            try { page.fields = JSON.parse(page.fields_json || '{}'); } catch { page.fields = {}; }
            return jsonResponse({ success: true, page });
        }
        if (method === 'PUT') {
            const body = await request.json();
            const updateBody = {
                has_draft: 1,
                updated_at: new Date().toISOString()
            };
            if (body.fields !== undefined) updateBody.fields_json = JSON.stringify(body.fields);
            if (body.meta_title !== undefined) updateBody.meta_title = body.meta_title;
            if (body.meta_description !== undefined) updateBody.meta_description = body.meta_description;
            if (body.meta_keywords !== undefined) updateBody.meta_keywords = body.meta_keywords;

            const res = await querySupabaseRaw(env, `pages?page_key=eq.${encodeURIComponent(pageKey)}`, {
                method: 'PATCH',
                prefer: 'return=representation',
                body: updateBody
            });
            if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            return jsonResponse({ success: true, message: 'Draft saved successfully.' });
        }
    }

    // 5. Work Items CRUD
    if (path === 'work' || path.startsWith('work/')) {
        return handleCrud(request, url, path, env, 'work_items');
    }

    // 6. Blog Posts CRUD
    if (path === 'blog' || path.startsWith('blog/')) {
        return handleCrud(request, url, path, env, 'blog_posts');
    }

    // 7. Jobs CRUD
    if (path === 'jobs' || path.startsWith('jobs/')) {
        return handleCrud(request, url, path, env, 'jobs');
    }

    // 8. Media Library
    if (path === 'media' && method === 'GET') {
        const rows = await querySupabase(env, 'media_assets?order=id.desc');
        return jsonResponse({ success: true, media: rows || [] });
    }

    if (path === 'media/add-url' && method === 'POST') {
        const body = await request.json();
        const fileUrl = (body.url || '').trim();
        if (!fileUrl) return jsonResponse({ detail: 'URL is required' }, 400);
        const payload = {
            filename: (body.filename || fileUrl.split('/').pop() || 'asset.webp').slice(0, 120),
            file_path: fileUrl,
            secure_url: fileUrl,
            file_size: 0,
            mime_type: 'image/webp',
            category: body.category || 'general',
            folder: body.folder || 'general',
            storage_provider: 'external_url',
            uploaded_at: new Date().toISOString()
        };
        const res = await querySupabaseRaw(env, 'media_assets', {
            method: 'POST',
            prefer: 'return=representation',
            body: payload
        });
        if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        return jsonResponse({ success: true, message: 'Media URL added successfully.', asset: res.data?.[0] || payload });
    }

    if (path === 'media/upload' && method === 'POST') {
        return handleMediaUpload(request, env);
    }

    if (path.startsWith('media/') && method === 'DELETE') {
        const id = path.replace('media/', '');
        const res = await querySupabaseRaw(env, `media_assets?id=eq.${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        return jsonResponse({ success: true, message: 'Media asset deleted.' });
    }

    // 9. User Management
    if (path === 'users' || path.startsWith('users/')) {
        return handleUsersAdmin(request, path, env);
    }

    return jsonResponse({ detail: 'Admin action not found' }, 404);
}

async function handleMediaUpload(request, env) {
    try {
        const formData = await request.formData();
        const file = formData.get('file');
        const folder = (formData.get('folder') || 'general').toString();

        if (!file || typeof file === 'string') {
            return jsonResponse({ detail: 'No file provided' }, 400);
        }

        if (file.size > 1500000) {
            return jsonResponse({
                detail: 'File is larger than 1.5 MB. For large files, paste an external/Cloudinary image URL via "Add Image URL".'
            }, 400);
        }

        const buf = await file.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192) {
            binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        }
        const base64 = btoa(binary);
        const mimeType = file.type || 'image/webp';
        const dataUrl = `data:${mimeType};base64,${base64}`;

        const payload = {
            filename: file.name || 'uploaded-image',
            file_path: dataUrl,
            secure_url: dataUrl,
            file_size: file.size || bytes.length,
            mime_type: mimeType,
            category: folder,
            folder,
            storage_provider: 'edge_inline',
            uploaded_at: new Date().toISOString()
        };

        const res = await querySupabaseRaw(env, 'media_assets', {
            method: 'POST',
            prefer: 'return=representation',
            body: payload
        });
        if (!res.ok) {
            return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        }
        return jsonResponse({
            success: true,
            message: 'Image uploaded successfully.',
            asset: res.data?.[0] || payload
        });
    } catch (e) {
        return jsonResponse({ detail: `Upload failed: ${e.message}` }, 500);
    }
}

async function handleUsersAdmin(request, path, env) {
    const parts = path.split('/');
    const method = request.method;

    if (parts.length === 1) {
        if (method === 'GET') {
            const rows = await querySupabase(env, 'users?select=id,email,full_name,role,status,created_at,last_login&order=id.asc');
            return jsonResponse({ success: true, users: rows || [] });
        }
        if (method === 'POST') {
            const body = await request.json();
            const now = new Date().toISOString();
            const payload = {
                email: (body.email || '').trim().toLowerCase(),
                full_name: (body.full_name || 'User').trim(),
                role: body.role || 'editor',
                status: body.status || 'active',
                created_at: now
            };
            const res = await querySupabaseRaw(env, 'users', {
                method: 'POST',
                prefer: 'return=representation',
                body: payload
            });
            if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            return jsonResponse({ success: true, message: 'User created.', user: res.data?.[0] || payload });
        }
    }

    const userId = parts[1];
    if (parts.length === 2) {
        if (method === 'PUT') {
            const body = await request.json();
            const payload = {};
            if (body.full_name !== undefined) payload.full_name = body.full_name;
            if (body.role !== undefined) payload.role = body.role;
            if (body.status !== undefined) payload.status = body.status;
            const res = await querySupabaseRaw(env, `users?id=eq.${encodeURIComponent(userId)}`, {
                method: 'PATCH',
                prefer: 'return=representation',
                body: payload
            });
            if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            return jsonResponse({ success: true, message: 'User updated.', user: res.data?.[0] });
        }
        if (method === 'DELETE') {
            const res = await querySupabaseRaw(env, `users?id=eq.${encodeURIComponent(userId)}`, { method: 'DELETE' });
            if (!res.ok) return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            return jsonResponse({ success: true, message: 'User deleted.' });
        }
    }

    if (parts.length === 3 && parts[2] === 'reset-password' && method === 'POST') {
        return jsonResponse({ success: true, message: 'Password reset recorded. Note: Master Edge Worker login uses ADMIN_PASSWORD from Cloudflare settings.' });
    }

    return jsonResponse({ detail: 'Invalid user operation' }, 400);
}

async function handleCrud(request, url, path, env, table) {
    const parts = path.split('/');
    const method = request.method;
    const singularKey = table === 'work_items' ? 'item' : table === 'blog_posts' ? 'post' : 'job';
    const listKey = table === 'work_items' ? 'items' : table === 'blog_posts' ? 'posts' : 'jobs';

    if (parts.length === 1) {
        if (method === 'GET') {
            const statusFilter = url.searchParams.get('status');
            let query = `${table}?order=${table === 'work_items' ? 'display_order.asc,id.desc' : 'id.desc'}`;
            if (statusFilter && statusFilter !== 'all') {
                query += `&status=eq.${encodeURIComponent(statusFilter)}`;
            }
            const res = await querySupabaseRaw(env, query);
            if (!res.ok) {
                return jsonResponse({ success: false, detail: `Database error: ${res.error}`, [listKey]: [] }, 500);
            }
            return jsonResponse({ success: true, [listKey]: res.data || [] });
        }
        if (method === 'POST') {
            const body = await request.json();
            delete body.id;
            const now = new Date().toISOString();
            body.created_at = now;
            body.updated_at = now;

            if (table === 'blog_posts') {
                if (!body.slug && body.title) {
                    body.slug = body.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '-' + Date.now().toString().slice(-4);
                }
                if (!body.published_date) {
                    body.published_date = now.slice(0, 10);
                }
            }

            const res = await querySupabaseRaw(env, table, {
                method: 'POST',
                prefer: 'return=representation',
                body
            });
            if (!res.ok) {
                return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            }
            const created = res.data?.[0] || body;
            return jsonResponse({ success: true, message: 'Created successfully', [singularKey]: created, item: created });
        }
    }

    const id = encodeURIComponent(parts[1]);
    if (parts.length === 2) {
        if (method === 'GET') {
            const rows = await querySupabase(env, `${table}?id=eq.${id}&limit=1`);
            if (!rows || !rows[0]) return jsonResponse({ detail: 'Not found' }, 404);
            return jsonResponse({ success: true, [singularKey]: rows[0], item: rows[0] });
        }
        if (method === 'PUT') {
            const body = await request.json();
            delete body.id;
            delete body.created_at;
            body.updated_at = new Date().toISOString();
            const res = await querySupabaseRaw(env, `${table}?id=eq.${id}`, {
                method: 'PATCH',
                prefer: 'return=representation',
                body
            });
            if (!res.ok) {
                return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            }
            const updated = res.data?.[0] || body;
            return jsonResponse({ success: true, message: 'Updated successfully', [singularKey]: updated, item: updated });
        }
        if (method === 'DELETE') {
            const res = await querySupabaseRaw(env, `${table}?id=eq.${id}`, { method: 'DELETE' });
            if (!res.ok) {
                return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
            }
            return jsonResponse({ success: true, message: 'Deleted successfully' });
        }
    }

    if (parts.length === 3 && method === 'POST') {
        const action = parts[2];
        const status = action === 'publish' ? 'published' : action === 'unpublish' ? 'draft' : action === 'close' ? 'closed' : 'draft';
        const res = await querySupabaseRaw(env, `${table}?id=eq.${id}`, {
            method: 'PATCH',
            prefer: 'return=representation',
            body: { status, updated_at: new Date().toISOString() }
        });
        if (!res.ok) {
            return jsonResponse({ detail: `Database error: ${res.error}` }, 500);
        }
        return jsonResponse({ success: true, message: `Status updated to ${status}` });
    }

    return jsonResponse({ detail: 'Invalid CRUD operation' }, 400);
}

// ----------------- EDGE SSR WITH HTMLREWRITER -----------------

async function handleHomepageSSR(request, env) {
    const response = await env.ASSETS.fetch(request);
    if (!response.ok) return response;

    const [videoRow, pagesRow, imagesRows] = await Promise.all([
        querySupabase(env, 'homepage_video_section?id=eq.1&select=*').catch(() => null),
        querySupabase(env, 'pages?page_key=eq.index&limit=1').catch(() => null),
        querySupabase(env, 'homepage_images?select=*').catch(() => null)
    ]);

    const videoData = videoRow?.[0];
    const pageData = pagesRow?.[0];
    let fields = {};
    try { fields = JSON.parse(pageData?.fields_json || '{}'); } catch {}

    let rewriter = new HTMLRewriter();

    if (fields.hero_badge) {
        const val = fields.hero_badge.current_value || fields.hero_badge.draft_value;
        if (val) rewriter = rewriter.on('span.pre-title', { element(e) { e.setInnerContent(val); } });
    }

    if (fields.hero_title) {
        const val = fields.hero_title.current_value || fields.hero_title.draft_value;
        if (val) {
            rewriter = rewriter.on('h1.title', {
                element(e) {
                    if (val.includes('Growing')) {
                        const parts = val.split('Growing');
                        e.setInnerContent(`${parts[0]}<span>Growing</span>${parts[1] || ''}`, { html: true });
                    } else {
                        e.setInnerContent(val);
                    }
                }
            });
        }
    }

    if (fields.hero_desc) {
        const val = fields.hero_desc.current_value || fields.hero_desc.draft_value;
        if (val) rewriter = rewriter.on('div.banner-wrapper-one p', { element(e) { e.setInnerContent(val); } });
    }

    if (videoData) {
        const isVideoOn = Boolean(videoData.video_enabled);
        const imgUrl = videoData.image_url || 'assets/images/video/01.webp';
        const imgAlt = videoData.image_alt || 'Engineering Process';

        rewriter = rewriter.on('div.image--large-video img', {
            element(e) {
                e.setAttribute('src', imgUrl);
                e.setAttribute('alt', imgAlt);
            }
        });

        if (!isVideoOn) {
            rewriter = rewriter.on('div.image--large-video div.vedio-icone', {
                element(e) {
                    e.setAttribute('style', 'display: none !important;');
                }
            });
        } else if (videoData.video_url) {
            rewriter = rewriter.on('div.image--large-video a.popup-video', {
                element(e) {
                    e.setAttribute('href', videoData.video_url);
                }
            });
        }
    }

    if (imagesRows && Array.isArray(imagesRows)) {
        imagesRows.forEach(slot => {
            if (slot.selector && slot.current_src) {
                rewriter = rewriter.on(slot.selector, {
                    element(e) {
                        e.setAttribute('src', slot.current_src);
                        if (slot.current_alt) e.setAttribute('alt', slot.current_alt);
                    }
                });
            }
        });
    }

    const transformedResponse = rewriter.transform(response);
    const newHeaders = new Headers(transformedResponse.headers);
    newHeaders.set('Cache-Control', 'no-cache, no-store, must-revalidate');
    newHeaders.set('X-Powered-By', 'Cloudflare-Worker-Codozent');

    return new Response(transformedResponse.body, {
        status: transformedResponse.status,
        headers: newHeaders
    });
}

async function handleBlogDetailsSSR(request, env, slug) {
    const response = await env.ASSETS.fetch(request);
    if (!response.ok) return response;

    const rows = await querySupabase(env, `blog_posts?slug=eq.${encodeURIComponent(slug)}&status=eq.published&limit=1`);
    if (!rows || rows.length === 0) {
        return new Response('Article Not Found', { status: 404 });
    }

    const post = rows[0];
    let rewriter = new HTMLRewriter()
        .on('title', { element(e) { e.setInnerContent(`${post.title} | Codozent Insights`); } })
        .on('div.top-title-area span.sub', { element(e) { e.setInnerContent(post.category || 'Insights'); } })
        .on('div.top-title-area h1.title', { element(e) { e.setInnerContent(post.title || ''); } })
        .on('div.thumbnail img', {
            element(e) {
                if (post.featured_image) e.setAttribute('src', post.featured_image);
                if (post.featured_image_alt) e.setAttribute('alt', post.featured_image_alt);
            }
        })
        .on('div.blog-listing-content', {
            element(e) {
                e.setInnerContent(post.body || '', { html: true });
            }
        });

    const transformedResponse = rewriter.transform(response);
    const newHeaders = new Headers(transformedResponse.headers);
    newHeaders.set('Cache-Control', 'no-cache, no-store, must-revalidate');
    return new Response(transformedResponse.body, {
        status: transformedResponse.status,
        headers: newHeaders
    });
}

function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': 'true'
        }
    });
}
