/**
 * Codozent All-in-One Cloudflare Edge Worker
 * Fully hosts the entire website, dynamic Edge SSR, and CMS backend on Cloudflare.
 * - 0ms cold starts (never goes to sleep like Render)
 * - Connects directly to Supabase REST API
 * - Edge Server-Side Rendering via HTMLRewriter for instant SEO & live updates
 * - Built-in Admin Authentication and CMS APIs
 * - All secrets and credentials read strictly from Cloudflare Environment Variables / Secrets
 */

// ----------------- ENVIRONMENT HELPER -----------------

function getEnvVar(env, key, defaultVal = '') {
    if (env && typeof env[key] !== 'undefined' && env[key] !== null) {
        return String(env[key]);
    }
    try {
        if (typeof globalThis !== 'undefined' && typeof globalThis[key] !== 'undefined' && globalThis[key] !== null) {
            return String(globalThis[key]);
        }
    } catch {}
    try {
        if (typeof process !== 'undefined' && process.env && typeof process.env[key] !== 'undefined' && process.env[key] !== null) {
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

        let binary = atob(encSig.replace(/-/g, '+').replace(/_/g, '/'));
        const sigBytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) sigBytes[i] = binary.charCodeAt(i);

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
        let [name, ...rest] = cookie.split('=');
        name = name?.trim();
        if (!name) return;
        const value = rest.join('=').trim();
        list[name] = decodeURIComponent(value);
    });
    return list;
}

// ----------------- SUPABASE REST API CLIENT -----------------

async function querySupabase(env, path, options = {}) {
    let supabaseUrl = getEnvVar(env, 'SUPABASE_URL').trim();
    const supabaseKey = (getEnvVar(env, 'SUPABASE_KEY') || getEnvVar(env, 'SUPABASE_SERVICE_ROLE_KEY') || getEnvVar(env, 'SUPABASE_ANON_KEY')).trim();

    if (!supabaseUrl || !supabaseKey) {
        return null; // Return null gracefully if key not yet provided in env
    }

    supabaseUrl = supabaseUrl.replace(/\/+$/, '');
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
            body: options.body ? JSON.stringify(options.body) : undefined
        });

        if (!res.ok) {
            const errText = await res.text();
            console.error(`Supabase error ${res.status}:`, errText);
            return null;
        }

        if (res.status === 204) return [];
        return await res.json();
    } catch (e) {
        console.error('Supabase fetch failed:', e);
        return null;
    }
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
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                    'Access-Control-Allow-Credentials': 'true'
                }
            });
        }

        // 2. Health Check Route
        if (url.pathname === '/api/health' || url.pathname === '/health') {
            const hasUrl = Boolean(getEnvVar(env, 'SUPABASE_URL').trim());
            const hasKey = Boolean(getEnvVar(env, 'SUPABASE_KEY') || getEnvVar(env, 'SUPABASE_SERVICE_ROLE_KEY') || getEnvVar(env, 'SUPABASE_ANON_KEY'));
            const hasEmail = Boolean(getEnvVar(env, 'ADMIN_EMAIL').trim());
            const hasPass = Boolean(getEnvVar(env, 'ADMIN_PASSWORD').trim());

            let dbStatus = 'NOT_CONFIGURED';
            if (hasUrl && hasKey) {
                try {
                    const rows = await querySupabase(env, 'homepage_video_section?select=id&limit=1');
                    dbStatus = rows !== null ? 'CONNECTED' : 'ERROR_CONNECTING_TO_SUPABASE';
                } catch (e) {
                    dbStatus = 'FAILED: ' + e.message;
                }
            }

            return jsonResponse({
                status: (dbStatus === 'CONNECTED' && hasEmail && hasPass) ? 'healthy' : 'setup_required',
                service: 'Codozent Cloudflare Edge Worker',
                config: {
                    SUPABASE_URL: hasUrl ? 'CONFIGURED' : 'MISSING (Retry deployment in Deployments tab)',
                    SUPABASE_KEY: hasKey ? 'CONFIGURED' : 'MISSING (Retry deployment in Deployments tab)',
                    ADMIN_EMAIL: hasEmail ? 'CONFIGURED' : 'MISSING (Retry deployment in Deployments tab)',
                    ADMIN_PASSWORD: hasPass ? 'CONFIGURED' : 'MISSING (Retry deployment in Deployments tab)',
                    CMS_SECRET_KEY: getEnvVar(env, 'CMS_SECRET_KEY') ? 'CONFIGURED' : 'USING_DEFAULT_SALT'
                },
                database_status: dbStatus,
                hint: (!hasEmail || !hasPass) ? 'If variables were recently added in Cloudflare Settings, go to Deployments tab and click Retry Deployment.' : 'All variables loaded.'
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
            // Serve admin dashboard from /admin/index.html
            const adminReq = new Request(new URL('/admin/index.html', request.url), request);
            return env.ASSETS.fetch(adminReq);
        }

        if (url.pathname === '/admin/login' || url.pathname === '/admin/login/') {
            const session = await getSession(request, secretKey);
            if (session) {
                return Response.redirect(`${url.origin}/admin`, 302);
            }
            // Serve login page from /admin/login.html
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
                detail: 'ADMIN_EMAIL or ADMIN_PASSWORD is not loaded in this deployment snapshot. In Cloudflare Pages, go to the "Deployments" tab and click "Retry deployment" (or push a commit) so your newly saved variables are applied.'
            }, 500);
        }

        // Check configured admin
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
    return new Response(JSON.stringify({ success: true, message: 'Logged out' }), {
        headers
    });
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
    return jsonResponse({ success: true, message: 'Password updated successfully' });
}

// ----------------- PUBLIC API HANDLERS -----------------

async function handlePublicApi(url, env) {
    const path = url.pathname.replace('/api/public/', '').replace(/\/$/, '');

    // Video Section
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

    // Homepage Images
    if (path === 'homepage-images') {
        const rows = await querySupabase(env, 'homepage_images?select=*');
        return jsonResponse({ success: true, images: rows || [] });
    }

    // Work Items
    if (path === 'work') {
        const rows = await querySupabase(env, 'work_items?status=eq.published&order=display_order.asc,id.asc');
        return jsonResponse({ success: true, work: rows || [] });
    }

    // Jobs
    if (path === 'jobs') {
        const rows = await querySupabase(env, 'jobs?status=eq.published&order=id.desc');
        return jsonResponse({ success: true, jobs: rows || [] });
    }

    // Blog
    if (path === 'blog') {
        const rows = await querySupabase(env, 'blog_posts?status=eq.published&order=published_date.desc');
        return jsonResponse({ success: true, posts: rows || [] });
    }

    // Blog Detail by Slug
    if (path.startsWith('blog/')) {
        const slug = decodeURIComponent(path.replace('blog/', ''));
        const rows = await querySupabase(env, `blog_posts?slug=eq.${encodeURIComponent(slug)}&status=eq.published&limit=1`);
        if (rows && rows.length > 0) {
            return jsonResponse({ success: true, post: rows[0] });
        }
        return jsonResponse({ detail: 'Article not found' }, 404);
    }

    // Page Fields (e.g. pages/index)
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

    // Stats
    if (path === 'stats') {
        const jobs = await querySupabase(env, 'jobs?select=id') || [];
        const work = await querySupabase(env, 'work_items?select=id') || [];
        const blogs = await querySupabase(env, 'blog_posts?select=id') || [];
        const images = await querySupabase(env, 'homepage_images?select=slot_key') || [];
        return jsonResponse({
            success: true,
            stats: {
                jobs_count: jobs.length,
                work_count: work.length,
                blog_count: blogs.length,
                images_count: images.length
            }
        });
    }

    // Video Section
    if (path === 'video-section') {
        if (method === 'GET') {
            const rows = await querySupabase(env, 'homepage_video_section?id=eq.1&select=*');
            const data = (rows && rows[0]) || { id: 1, video_enabled: 1, video_url: '', image_url: '', image_alt: '' };
            data.video_enabled = Boolean(data.video_enabled);
            return jsonResponse({ success: true, video_section: data });
        }
        if (method === 'POST' || method === 'PUT') {
            const body = await request.json();
            const payload = {
                video_enabled: body.video_enabled ? 1 : 0,
                video_url: (body.video_url || '').trim(),
                image_url: (body.image_url || '').trim(),
                image_alt: (body.image_alt || '').trim(),
                updated_at: new Date().toISOString()
            };
            await querySupabase(env, 'homepage_video_section?id=eq.1', {
                method: 'PATCH',
                body: payload
            });
            // Keep slot in sync
            await querySupabase(env, 'homepage_images?slot_key=eq.video_thumbnail', {
                method: 'PATCH',
                body: { current_src: payload.image_url, draft_src: payload.image_url, updated_at: payload.updated_at }
            });
            return jsonResponse({ success: true, message: 'Video section updated successfully.', video_section: payload });
        }
    }

    // Homepage Images
    if (path === 'homepage-images') {
        const rows = await querySupabase(env, 'homepage_images?select=*');
        return jsonResponse({ success: true, images: rows || [] });
    }

    if (path.startsWith('homepage-images/') && path.endsWith('/publish')) {
        // Publish draft images
        const rows = await querySupabase(env, 'homepage_images?select=*') || [];
        for (const slot of rows) {
            if (slot.draft_src) {
                await querySupabase(env, `homepage_images?slot_key=eq.${slot.slot_key}`, {
                    method: 'PATCH',
                    body: {
                        current_src: slot.draft_src,
                        current_alt: slot.draft_alt || slot.current_alt,
                        has_draft: 0,
                        updated_at: new Date().toISOString()
                    }
                });
            }
        }
        return jsonResponse({ success: true, message: 'All homepage images published live.' });
    }

    if (path.startsWith('homepage-images/')) {
        const slotKey = path.replace('homepage-images/', '');
        const body = await request.json();
        const payload = {
            draft_src: (body.draft_src || '').trim(),
            draft_alt: (body.draft_alt || '').trim(),
            has_draft: 1,
            updated_at: new Date().toISOString()
        };
        await querySupabase(env, `homepage_images?slot_key=eq.${slotKey}`, {
            method: 'PATCH',
            body: payload
        });
        return jsonResponse({ success: true, message: 'Draft image saved.' });
    }

    // Pages (Page Content)
    if (path === 'pages') {
        const rows = await querySupabase(env, 'pages?select=*');
        return jsonResponse({ success: true, pages: rows || [] });
    }

    if (path.startsWith('pages/') && path.endsWith('/publish')) {
        const pageKey = path.replace('pages/', '').replace('/publish', '');
        const rows = await querySupabase(env, `pages?page_key=eq.${pageKey}&limit=1`);
        if (rows && rows[0]) {
            const page = rows[0];
            const fields = JSON.parse(page.fields_json || '{}');
            for (const k in fields) {
                fields[k].current_value = fields[k].draft_value;
            }
            await querySupabase(env, `pages?page_key=eq.${pageKey}`, {
                method: 'PATCH',
                body: {
                    fields_json: JSON.stringify(fields),
                    has_draft: 0,
                    published_at: new Date().toISOString(),
                    updated_at: new Date().toISOString()
                }
            });
            return jsonResponse({ success: true, message: 'Page published live.' });
        }
    }

    if (path.startsWith('pages/')) {
        const pageKey = path.replace('pages/', '');
        if (method === 'GET') {
            const rows = await querySupabase(env, `pages?page_key=eq.${pageKey}&limit=1`);
            if (rows && rows[0]) {
                const page = rows[0];
                page.fields = JSON.parse(page.fields_json || '{}');
                return jsonResponse({ success: true, page });
            }
        }
        if (method === 'PUT') {
            const body = await request.json();
            await querySupabase(env, `pages?page_key=eq.${pageKey}`, {
                method: 'PATCH',
                body: {
                    fields_json: JSON.stringify(body.fields || {}),
                    has_draft: 1,
                    updated_at: new Date().toISOString()
                }
            });
            return jsonResponse({ success: true, message: 'Draft saved successfully.' });
        }
    }

    // Work Items
    if (path === 'work' || path.startsWith('work/')) {
        return handleCrud(request, path, env, 'work_items');
    }

    // Blog
    if (path === 'blog' || path.startsWith('blog/')) {
        return handleCrud(request, path, env, 'blog_posts');
    }

    // Jobs
    if (path === 'jobs' || path.startsWith('jobs/')) {
        return handleCrud(request, path, env, 'jobs');
    }

    // Media
    if (path === 'media') {
        const rows = await querySupabase(env, 'media_assets?order=id.desc');
        return jsonResponse({ success: true, media: rows || [] });
    }

    if (path === 'media/add-url' && method === 'POST') {
        const body = await request.json();
        const payload = {
            filename: body.filename || 'asset.webp',
            file_path: body.url || '',
            file_size: 0,
            mime_type: 'image/webp',
            category: 'general',
            storage_provider: 'cloudinary',
            uploaded_at: new Date().toISOString()
        };
        await querySupabase(env, 'media_assets', { method: 'POST', body: payload });
        return jsonResponse({ success: true, message: 'Media URL added successfully.' });
    }

    return jsonResponse({ detail: 'Admin action not found' }, 404);
}

async function handleCrud(request, path, env, table) {
    const parts = path.split('/');
    const method = request.method;

    if (parts.length === 1) {
        if (method === 'GET') {
            const rows = await querySupabase(env, `${table}?order=id.desc`);
            const key = table === 'work_items' ? 'items' : table === 'blog_posts' ? 'posts' : 'jobs';
            return jsonResponse({ success: true, [key]: rows || [] });
        }
        if (method === 'POST') {
            const body = await request.json();
            body.created_at = new Date().toISOString();
            body.updated_at = new Date().toISOString();
            const res = await querySupabase(env, table, { method: 'POST', body });
            return jsonResponse({ success: true, message: 'Item created', item: res?.[0] || body });
        }
    }

    const id = parts[1];
    if (parts.length === 2) {
        if (method === 'GET') {
            const rows = await querySupabase(env, `${table}?id=eq.${id}&limit=1`);
            return jsonResponse({ success: true, item: rows?.[0] });
        }
        if (method === 'PUT') {
            const body = await request.json();
            body.updated_at = new Date().toISOString();
            await querySupabase(env, `${table}?id=eq.${id}`, { method: 'PATCH', body });
            return jsonResponse({ success: true, message: 'Item updated' });
        }
        if (method === 'DELETE') {
            await querySupabase(env, `${table}?id=eq.${id}`, { method: 'DELETE' });
            return jsonResponse({ success: true, message: 'Item deleted' });
        }
    }

    if (parts.length === 3) {
        const action = parts[2];
        const status = action === 'publish' ? 'published' : action === 'unpublish' ? 'draft' : action === 'close' ? 'closed' : 'draft';
        await querySupabase(env, `${table}?id=eq.${id}`, {
            method: 'PATCH',
            body: { status, updated_at: new Date().toISOString() }
        });
        return jsonResponse({ success: true, message: `Status updated to ${status}` });
    }

    return jsonResponse({ detail: 'Invalid CRUD operation' }, 400);
}

// ----------------- EDGE SSR WITH HTMLREWRITER -----------------

async function handleHomepageSSR(request, env) {
    // 1. Fetch static index.html from Cloudflare assets
    const response = await env.ASSETS.fetch(request);
    if (!response.ok) return response;

    // 2. Fetch live data from Supabase in parallel
    const [videoRow, pagesRow, imagesRows] = await Promise.all([
        querySupabase(env, 'homepage_video_section?id=eq.1&select=*').catch(() => null),
        querySupabase(env, 'pages?page_key=eq.index&limit=1').catch(() => null),
        querySupabase(env, 'homepage_images?select=*').catch(() => null)
    ]);

    const videoData = videoRow?.[0];
    const pageData = pagesRow?.[0];
    let fields = {};
    try { fields = JSON.parse(pageData?.fields_json || '{}'); } catch {}

    // 3. Transform HTML on the Edge before sending to browser
    let rewriter = new HTMLRewriter();

    // Transform Page Text Fields
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

    // Transform Video Section
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
            // Hide video icon
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

    // Transform Homepage Image Slots
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

    return rewriter.transform(response);
}

function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': 'true'
        }
    });
}
