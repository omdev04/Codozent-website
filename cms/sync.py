"""
Codozent CMS Synchronization & Publishing Engine
Synchronizes SQLite data with static HTML templates:
- index.html (Homepage sections, images, and Latest Insights!)
- career.html (Career culture & live job openings or honest No Openings empty state)
- blog.html & blog-grid.html (Published articles listing)
- blog-details.html (Detail template rendering)
- sitemap.xml (SEO sitemap updated on every publish/delete)
- Strictly preserves template styles, CSS classes, responsive grids, and the navbar.
"""
import os
import json
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from cms.db import get_db_connection

logger = logging.getLogger("CodozentCMS.sync")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def trigger_cloudflare_pages_deploy() -> bool:
    """
    Triggers Cloudflare Pages automated rebuild & redeploy via Deploy Hook URL.
    Called whenever CMS content (blogs, jobs, work items, homepage images) is published or deleted
    in a Hybrid Cloudflare Pages + Render/VPS setup.
    """
    hook_url = os.environ.get("CLOUDFLARE_PAGES_DEPLOY_HOOK")
    if not hook_url or not hook_url.strip():
        return False

    try:
        import urllib.request
        req = urllib.request.Request(hook_url.strip(), data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("Cloudflare Pages deploy hook triggered successfully (HTTP %s)", resp.status)
            return True
    except Exception as e:
        logger.warning("Could not trigger Cloudflare Pages deploy hook: %s", e)
        return False

# Define editable text fields for main pages
PAGE_DEFINITIONS = {
    "index": {
        "title": "Home Page",
        "file_name": "index.html",
        "fields": [
            {"key": "hero_badge", "label": "Hero Top Badge", "section": "Hero Banner", "type": "text", "default": "Smart, Stable, Future-Ready Technology"},
            {"key": "hero_title", "label": "Hero Main Headline", "section": "Hero Banner", "type": "textarea", "default": "Engineering Dependable Solutions for Growing Businesses"},
            {"key": "hero_desc", "label": "Hero Description", "section": "Hero Banner", "type": "textarea", "default": "Codozent Technologies partners with businesses to build high-performance web applications, mobile applications, bespoke software, and automated operational tools."},
            {"key": "hero_cta_text", "label": "Hero CTA Button Text", "section": "Hero Banner", "type": "text", "default": "Explore Services"},
            {"key": "video_title_1", "label": "Philosophy Large Lead", "section": "Video Philosophy", "type": "textarea", "default": "We engineer clean, stable and dependable digital platforms to streamline operations and to accelerate business growth."},
            {"key": "video_desc", "label": "Philosophy Description", "section": "Video Philosophy", "type": "textarea", "default": "Codozent Technologies combines pragmatic architecture with milestone-based delivery to help organizations build maintainable, scalable digital products."},
            {"key": "services_heading", "label": "Services Section Heading", "section": "Services Overview", "type": "text", "default": "Software Engineering Services"},
            {"key": "services_subheading", "label": "Services Subheading", "section": "Services Overview", "type": "textarea", "default": "Tailored software engineering and digital solutions built for stability, security, and measurable performance."},
            {"key": "cta_box_title", "label": "Footer Callout Title", "section": "Footer Callout", "type": "text", "default": "Ready to Build Something Stable and Scalable?"},
            {"key": "cta_box_desc", "label": "Footer Callout Description", "section": "Footer Callout", "type": "textarea", "default": "Whether you need a web platform, a mobile app, or pilot access to our modular ERP, we're ready to discuss your requirements."}
        ]
    },
    "about": {
        "title": "About Us",
        "file_name": "about.html",
        "fields": [
            {"key": "hero_badge", "label": "About Hero Badge", "section": "Hero", "type": "text", "default": "About Codozent Technologies"},
            {"key": "hero_title", "label": "About Hero Title", "section": "Hero", "type": "text", "default": "Engineering Dependable Software for Real Business Needs"},
            {"key": "hero_desc", "label": "About Hero Description", "section": "Hero", "type": "textarea", "default": "At Codozent Technologies, we specialize in high-performance web applications, mobile solutions, custom system integrations, and modern enterprise software."},
            {"key": "mission_title", "label": "Core Mission Title", "section": "Mission", "type": "text", "default": "Pragmatic Architecture, Reliable Delivery"},
            {"key": "mission_desc", "label": "Core Mission Statement", "section": "Mission", "type": "textarea", "default": "We believe modern software should be stable, maintainable, and aligned directly with operational outcomes rather than transient buzzwords."}
        ]
    },
    "service": {
        "title": "Services Overview",
        "file_name": "service.html",
        "fields": [
            {"key": "hero_badge", "label": "Service Badge", "section": "Hero", "type": "text", "default": "Software Engineering Services"},
            {"key": "hero_title", "label": "Service Hero Title", "section": "Hero", "type": "text", "default": "Engineering Dependable Digital Solutions"},
            {"key": "hero_desc", "label": "Service Hero Description", "section": "Hero", "type": "textarea", "default": "Codozent Technologies partners with growing businesses to engineer high-performance web applications, cross-platform mobile apps, bespoke software solutions, and automated operational tools."},
            {"key": "approach_desc", "label": "Engineering Approach", "section": "Philosophy", "type": "textarea", "default": "Our engineering philosophy centers on clean code, stable architectures, and milestone-based execution. We avoid transient hype and brittle frameworks, focusing instead on maintainable technology stacks that scale smoothly with your business."}
        ]
    },
    "products": {
        "title": "Products & Roadmap",
        "file_name": "products.html",
        "fields": [
            {"key": "hero_badge", "label": "Product Badge", "section": "Hero", "type": "text", "default": "Innovation & Product Roadmap"},
            {"key": "hero_title", "label": "Product Hero Title", "section": "Hero", "type": "text", "default": "Products in Development & Upcoming Launches"},
            {"key": "hero_desc", "label": "Product Hero Description", "section": "Hero", "type": "textarea", "default": "In addition to delivering bespoke software for clients, Codozent Technologies is actively engineering proprietary software platforms designed to solve critical operational bottlenecks."}
        ]
    },
    "career": {
        "title": "Careers",
        "file_name": "career.html",
        "fields": [
            {"key": "hero_title", "label": "Career Hero Title", "section": "Hero", "type": "text", "default": "Engineering Culture at Codozent Technologies"},
            {"key": "hero_desc", "label": "Career Hero Description", "section": "Hero", "type": "textarea", "default": "We believe that outstanding software is built by thoughtful engineers working in a culture of autonomy, craftsmanship, and transparent communication. We value clean, maintainable code over quick hacks, and pragmatic problem-solving over hype."},
            {"key": "why_work_title", "label": "Why Work With Us Title", "section": "Culture", "type": "text", "default": "Why Work With Us?"},
            {"key": "why_work_desc", "label": "Why Work With Us Description", "section": "Culture", "type": "textarea", "default": "We provide a collaborative, transparent engineering environment where every developer contributes directly to architectural decisions and client outcomes."},
            {"key": "openings_title", "label": "Openings Section Title", "section": "Openings", "type": "text", "default": "Current Openings"},
            {"key": "openings_subtitle", "label": "Openings Section Subtitle", "section": "Openings", "type": "text", "default": "Accurate status of active job openings at Codozent Technologies"}
        ]
    },
    "blog": {
        "title": "Blog & Insights",
        "file_name": "blog.html",
        "fields": [
            {"key": "hero_badge", "label": "Blog Pre-Title", "section": "Hero", "type": "text", "default": "Technical Perspectives"},
            {"key": "hero_title", "label": "Blog Main Title", "section": "Hero", "type": "text", "default": "Blog & Engineering Insights"},
            {"key": "hero_desc", "label": "Blog Description", "section": "Hero", "type": "textarea", "default": "Articles and architecture breakdowns from the Codozent Technologies team on modern web performance, modular ERP design, and reliable system integrations."}
        ]
    },
    "contact": {
        "title": "Contact Us",
        "file_name": "contact.html",
        "fields": [
            {"key": "hero_title", "label": "Contact Main Title", "section": "Hero", "type": "text", "default": "Get in Touch"},
            {"key": "hero_desc", "label": "Contact Subtitle", "section": "Hero", "type": "textarea", "default": "We'd love to discuss your project requirements, technical architecture, or pilot inquiries."}
        ]
    }
}

HOMEPAGE_IMAGE_SLOTS = [
    {
        "slot_key": "hero_1",
        "label": "Hero Image 1 (Engineering Team)",
        "section": "Hero Banner",
        "selector": "div.banner-wrapper-one + div div.left-image:nth-of-type(1) img",
        "current_src": "assets/images/banner/08.webp",
        "current_alt": "Codozent Engineering",
        "recommended_dims": "450x550 px (Portrait / Team)"
    },
    {
        "slot_key": "hero_2",
        "label": "Hero Image 2 (Software Architecture)",
        "section": "Hero Banner",
        "selector": "div.banner-wrapper-one + div div.left-image:nth-of-type(2) img",
        "current_src": "assets/images/banner/09.webp",
        "current_alt": "Software Architecture",
        "recommended_dims": "450x550 px (Portrait / Tech)"
    },
    {
        "slot_key": "video_thumbnail",
        "label": "Philosophy Video Section Image",
        "section": "Engineering Process",
        "selector": "div.image--large-video img",
        "current_src": "assets/images/video/01.webp",
        "current_alt": "Engineering Process",
        "recommended_dims": "1170x520 px (Wide)"
    },
    {
        "slot_key": "case_study_1",
        "label": "Work 1: Web Engineering Preview",
        "section": "Case Studies",
        "selector": "div.case-study-single:nth-of-type(1) img",
        "current_src": "assets/images/case-studies/01.webp",
        "current_alt": "Web Engineering",
        "recommended_dims": "600x400 px"
    },
    {
        "slot_key": "case_study_2",
        "label": "Work 2: Mobile Architecture Preview",
        "section": "Case Studies",
        "selector": "div.case-study-single:nth-of-type(2) img",
        "current_src": "assets/images/case-studies/02.webp",
        "current_alt": "Mobile Architecture",
        "recommended_dims": "600x400 px"
    },
    {
        "slot_key": "case_study_3",
        "label": "Work 3: Enterprise ERP Preview",
        "section": "Case Studies",
        "selector": "div.case-study-single:nth-of-type(3) img",
        "current_src": "assets/images/case-studies/03.webp",
        "current_alt": "Enterprise ERP",
        "recommended_dims": "600x400 px"
    },
    {
        "slot_key": "case_study_4",
        "label": "Work 4: API Integrations Preview",
        "section": "Case Studies",
        "selector": "div.case-study-single:nth-of-type(4) img",
        "current_src": "assets/images/case-studies/04.webp",
        "current_alt": "API Integrations",
        "recommended_dims": "600x400 px"
    }
]

INITIAL_BLOG_POSTS = [
    {
        "title": "Building Resilient Web Applications for Scale",
        "slug": "building-resilient-web-applications-for-scale",
        "excerpt": "Key considerations when structuring modern frontend and backend architectures for long-term maintainability and sub-second performance.",
        "body": """
        <p>Scaling a web application involves much more than simply adding server capacity. True resilience begins at the code and architecture level. In this article, our engineering team explores pragmatic decisions that prevent technical debt from slowing down business growth.</p>
        <h3>1. Keeping Component Boundaries Clean</h3>
        <p>Modular components allow frontend codebases to evolve safely. By separating business logic from visual representation, engineering teams can update styling and UX flows without risking regressions in core business operations.</p>
        <h3>2. Performance as an Architectural Requirement</h3>
        <p>Rather than treating speed optimization as an afterthought, establish performance budgets early. Minimizing third-party scripts, leveraging optimized asset compression, and ensuring sub-second first-contentful paint are essential for both search visibility and conversion rates.</p>
        <h3>3. Graceful Failure and API Resilience</h3>
        <p>Distributed systems inevitably experience transient network failures. Implementing structured retry queues, exponential backoff, and informative fallback UI states ensures that users remain informed rather than stranded on unresponsive screens.</p>
        """,
        "author": "Codozent Engineering Team",
        "author_role": "Software Architecture",
        "category": "Web Architecture",
        "tags": "Web, Performance, Architecture",
        "featured_image": "assets/images/blog/01.webp",
        "featured_image_alt": "Web Architecture Details",
        "published_date": "2026-11-20",
        "status": "published"
    },
    {
        "title": "Modular ERP Systems vs. Monolithic Suites",
        "slug": "modular-erp-systems-vs-monolithic-suites",
        "excerpt": "Why growing businesses benefit from lightweight, modular operational tools over rigid legacy enterprise platforms.",
        "body": """
        <p>Enterprise Resource Planning (ERP) systems have historically been dominated by monolithic platforms that require months of configuration, specialized consultants, and steep ongoing maintenance costs.</p>
        <h3>The Shift Toward Modular Operational Tools</h3>
        <p>Modern businesses require agile systems that integrate directly with their active workflows rather than forcing teams to overhaul their processes to fit rigid software constraints.</p>
        <h3>Core Benefits of Modular Architecture</h3>
        <ul>
            <li><strong>Gradual Adoption:</strong> Implement inventory or billing modules without committing to an all-or-nothing migration.</li>
            <li><strong>Direct API Integrations:</strong> Connect with modern payment gateways, messaging APIs, and accounting platforms.</li>
            <li><strong>Performance &amp; Maintainability:</strong> Lightweight databases and fast query responses without bloated legacy schemas.</li>
        </ul>
        """,
        "author": "Codozent Product Team",
        "author_role": "Product Roadmap",
        "category": "Enterprise Systems",
        "tags": "ERP, Architecture, Business Operations",
        "featured_image": "assets/images/blog/02.webp",
        "featured_image_alt": "Modular ERP Systems",
        "published_date": "2026-11-18",
        "status": "published"
    },
    {
        "title": "Integrating Custom Workflows with Third-Party APIs",
        "slug": "integrating-custom-workflows-with-third-party-apis",
        "excerpt": "Best practices for building robust data synchronization pipelines and handling external API reliability across distributed systems.",
        "body": """
        <p>Third-party APIs enable businesses to leverage specialized services like messaging, payment processing, and mapping without reinventing the wheel. However, relying on external services introduces real architectural risks that must be handled defensively.</p>
        <h3>Idempotency and Webhook Handling</h3>
        <p>Always assume webhooks can arrive out of order or be delivered multiple times. Ensure your ingress endpoints record transaction IDs and implement idempotent handlers before triggering downstream actions.</p>
        <h3>Rate Limiting and Circuit Breakers</h3>
        <p>Design your system with queue-based dispatchers that throttle requests within vendor limits. When an external service is degraded, circuit breakers should fail gracefully to prevent cascading timeouts across your application.</p>
        """,
        "author": "Codozent Engineering Team",
        "author_role": "System Integrations",
        "category": "System Integrations",
        "tags": "API, Integrations, Distributed Systems",
        "featured_image": "assets/images/blog/03.webp",
        "featured_image_alt": "System Integrations",
        "published_date": "2026-11-15",
        "status": "published"
    }
]

INITIAL_WORK_ITEMS = [
    {
        "title": "High-Performance Responsive Web Portals",
        "category": "Website Development, Performance",
        "description": "Component-driven frontend architecture utilizing modern JavaScript frameworks, responsive layouts, automated image optimization, and clean headless CMS integration for fast, accessible web applications.",
        "image_url": "assets/images/case-studies/01.webp",
        "image_alt": "Web Engineering",
        "project_url": "case-studies.html",
        "display_order": 1,
        "status": "published"
    },
    {
        "title": "Cross-Platform Mobile Application Architecture",
        "category": "Mobile Engineering, Cross-Platform",
        "description": "Cross-platform iOS and Android mobile engineering utilizing shared business logic, native performance hooks, offline data synchronization, and biometric authentication.",
        "image_url": "assets/images/case-studies/02.webp",
        "image_alt": "Mobile Architecture",
        "project_url": "case-studies.html",
        "display_order": 2,
        "status": "published"
    },
    {
        "title": "Modular ERP Data & Billing Pipeline",
        "category": "Enterprise Systems, In Development",
        "description": "Event-driven transactional data pipeline designed for order processing, recurring subscription billing, GST invoice calculation, and automated inventory reconciliation.",
        "image_url": "assets/images/case-studies/03.webp",
        "image_alt": "Enterprise ERP",
        "project_url": "erp-platform.html",
        "display_order": 3,
        "status": "published"
    },
    {
        "title": "Third-Party Integrations & Secure API Bridges",
        "category": "Custom Software & Integrations",
        "description": "Hardened REST and webhook integration layer connecting ERP data with CRM systems, payment gateways, and WhatsApp notifications.",
        "image_url": "assets/images/case-studies/04.webp",
        "image_alt": "API Integration",
        "project_url": "case-studies.html",
        "display_order": 4,
        "status": "published"
    }
]

def seed_content():
    """Seeds initial pages and image slots only once. Does NOT re-seed deleted blog posts on server restarts!"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()

    # Check if initial seeding was already completed
    cursor.execute("SELECT value FROM system_settings WHERE key = 'initial_seed_completed'")
    seed_flag = cursor.fetchone()

    # 1. Seed Pages
    for page_key, defn in PAGE_DEFINITIONS.items():
        cursor.execute("SELECT page_key FROM pages WHERE page_key = ?", (page_key,))
        if not cursor.fetchone():
            fields_data = {}
            for fld in defn["fields"]:
                fields_data[fld["key"]] = {
                    "label": fld["label"],
                    "section": fld["section"],
                    "type": fld["type"],
                    "current_value": fld["default"],
                    "draft_value": fld["default"]
                }
            cursor.execute(
                """
                INSERT INTO pages (page_key, title, file_name, meta_title, meta_description, fields_json, has_draft, updated_at, published_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    page_key,
                    defn["title"],
                    defn["file_name"],
                    f"{defn['title']} | Codozent Technologies",
                    f"Official {defn['title'].lower()} of Codozent Technologies.",
                    json.dumps(fields_data),
                    now_str,
                    now_str
                )
            )

    # 2. Seed Homepage Images
    for slot in HOMEPAGE_IMAGE_SLOTS:
        cursor.execute("SELECT slot_key FROM homepage_images WHERE slot_key = ?", (slot["slot_key"],))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO homepage_images (slot_key, label, section, selector, current_src, draft_src, current_alt, draft_alt, recommended_dims, has_draft, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    slot["slot_key"],
                    slot["label"],
                    slot["section"],
                    slot["selector"],
                    slot["current_src"],
                    slot["current_src"],
                    slot["current_alt"],
                    slot["current_alt"],
                    slot["recommended_dims"],
                    now_str
                )
            )

    # 3. Seed Blog Posts ONLY IF NOT ALREADY SEEDED (prevent resurrection of deleted posts)
    if not seed_flag:
        cursor.execute("SELECT COUNT(*) FROM blog_posts")
        count = cursor.fetchone()[0]
        if count == 0:
            for post in INITIAL_BLOG_POSTS:
                cursor.execute(
                    """
                    INSERT INTO blog_posts (title, slug, excerpt, body, author, author_role, category, tags, featured_image, featured_image_alt, published_date, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post["title"],
                        post["slug"],
                        post["excerpt"],
                        post["body"],
                        post["author"],
                        post["author_role"],
                        post["category"],
                        post["tags"],
                        post["featured_image"],
                        post["featured_image_alt"],
                        post["published_date"],
                        post["status"],
                        now_str,
                        now_str
                    )
                )
        cursor.execute("""
        INSERT OR IGNORE INTO homepage_video_section (id, video_enabled, video_url, image_url, image_alt, updated_at)
        VALUES (1, 1, 'https://www.youtube.com/watch?v=vZE0j_WCRvI', 'assets/images/video/01.webp', 'Engineering Process', ?)
        """, (now_str,))
        cursor.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('initial_seed_completed', '1', ?)",
            (now_str,)
        )

    # 4. Seed Work / Case Studies Portfolio Items (guarded to prevent resurrection if deleted)
    cursor.execute("SELECT value FROM system_settings WHERE key = 'work_items_seeded'")
    work_seed_flag = cursor.fetchone()
    if not work_seed_flag:
        cursor.execute("SELECT COUNT(*) FROM work_items")
        if cursor.fetchone()[0] == 0:
            for item in INITIAL_WORK_ITEMS:
                cursor.execute(
                    """
                    INSERT INTO work_items (title, category, description, image_url, image_alt, project_url, display_order, status, storage_provider, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', ?, ?)
                    """,
                    (
                        item["title"],
                        item["category"],
                        item["description"],
                        item["image_url"],
                        item["image_alt"],
                        item["project_url"],
                        item["display_order"],
                        item["status"],
                        now_str,
                        now_str
                    )
                )
        cursor.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('work_items_seeded', '1', ?)",
            (now_str,)
        )

    conn.commit()
    conn.close()
    logger.info("Content database verified.")

def regenerate_blog_page():
    """
    CRITICAL SYNCHRONIZATION FUNCTION:
    Regenerates:
    1. blog.html (public blog listing)
    2. blog-grid.html (secondary grid listing)
    3. index.html (Homepage 'Latest insights' section - PREVENTS STALE DELETED POSTS!)
    4. sitemap.xml (SEO sitemap with only published posts)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE status = 'published' ORDER BY published_date DESC, id DESC")
    published_posts = cursor.fetchall()
    conn.close()

    # ----------------------------------------------------
    # 1. Update blog.html & blog-grid.html
    # ----------------------------------------------------
    for listing_file in ["blog.html", "blog-grid.html"]:
        file_path = os.path.join(ROOT_DIR, listing_file)
        if not os.path.exists(file_path):
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        blog_area = soup.find("div", class_="rts-blog-area")
        if blog_area:
            cards_row = blog_area.find("div", class_="row")
            if cards_row:
                cards_row.clear()

                if len(published_posts) == 0:
                    # Empty state
                    col = soup.new_tag("div", **{"class": "col-12 text-center py-5"})
                    card = soup.new_tag("div", **{"style": "padding: 50px 20px; background: #ffffff; border: 1px solid #D8E5F8; border-radius: 12px; max-width: 600px; margin: 0 auto;"})
                    icon_div = soup.new_tag("div", **{"style": "width: 50px; height: 50px; background: #f0f4ff; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px;"})
                    icon = soup.new_tag("i", **{"class": "fa-regular fa-newspaper", "style": "font-size: 20px; color: #1363DF;"})
                    icon_div.append(icon)
                    card.append(icon_div)
                    h4 = soup.new_tag("h4", **{"style": "font-size: 18px; color: #081836; margin-bottom: 8px;"})
                    h4.string = "No Articles Currently Published"
                    card.append(h4)
                    p = soup.new_tag("p", **{"style": "font-size: 14px; color: #64748B; margin: 0;"})
                    p.string = "New technical perspectives and engineering deep-dives will be posted soon."
                    card.append(p)
                    col.append(card)
                    cards_row.append(col)
                else:
                    for i, post in enumerate(published_posts):
                        col = soup.new_tag("div", **{"class": "col-lg-4 col-md-6 col-sm-12"})
                        border_class = "border-left" if i == 0 else ""
                        item_wrap = soup.new_tag("div", **{"class": f"single-blog-area-start {border_class}".strip()})

                        # Thumbnail link
                        thumb_a = soup.new_tag("a", href=f"blog-details.html?slug={post['slug']}", **{"class": "thumbnail"})
                        img = soup.new_tag("img", src=post["featured_image"], alt=post["featured_image_alt"], loading="lazy", rel="preload")
                        thumb_a.append(img)
                        item_wrap.append(thumb_a)

                        # Content area
                        inner = soup.new_tag("div", **{"class": "inner-content-area"})
                        top_area = soup.new_tag("div", **{"class": "top-area"})
                        
                        cat_span = soup.new_tag("span")
                        cat_span.string = post["category"]
                        top_area.append(cat_span)

                        title_a = soup.new_tag("a", href=f"blog-details.html?slug={post['slug']}")
                        h3 = soup.new_tag("h3", **{"class": "title"})
                        h3.string = post["title"]
                        title_a.append(h3)
                        top_area.append(title_a)

                        disc_p = soup.new_tag("p", **{"class": "disc"})
                        disc_p.string = post["excerpt"]
                        top_area.append(disc_p)

                        # Author area
                        author_div = soup.new_tag("div", **{"class": "bottom-author-area"})
                        avatar_img = soup.new_tag("img", src="assets/images/testimonials/01.png", alt="author", loading="lazy", rel="preload")
                        author_div.append(avatar_img)

                        info_div = soup.new_tag("div", **{"class": "author-area-info"})
                        h6 = soup.new_tag("h6", **{"class": "title"})
                        h6.string = post["author"]
                        info_div.append(h6)
                        role_span = soup.new_tag("span")
                        role_span.string = post["author_role"] or post["category"]
                        info_div.append(role_span)
                        author_div.append(info_div)

                        top_area.append(author_div)
                        inner.append(top_area)
                        item_wrap.append(inner)
                        col.append(item_wrap)
                        cards_row.append(col)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(str(soup))

    # ----------------------------------------------------
    # 2. Update index.html (Homepage 'Latest insights' section)
    # ROOT CAUSE FIX: Deleted articles MUST be removed from homepage!
    # ----------------------------------------------------
    index_path = os.path.join(ROOT_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Find "Latest insights" title
        latest_title = None
        for h2 in soup.find_all("h2"):
            if "Latest insights" in h2.get_text():
                latest_title = h2
                break

        if latest_title:
            # Navigate to the container after the title container
            parent_container = latest_title.find_parent("div", class_="container")
            if parent_container:
                insights_container = parent_container.find_next_sibling("div", class_="container")
                if insights_container:
                    cards_row = insights_container.find("div", class_="row")
                    if cards_row:
                        cards_row.clear()

                        if len(published_posts) == 0:
                            # If no posts, render clean notice
                            col = soup.new_tag("div", **{"class": "col-12 text-center py-4"})
                            p = soup.new_tag("p", **{"style": "color: #64748B; font-size: 15px;"})
                            p.string = "Engineering insights and articles are being prepared. Check back soon."
                            col.append(p)
                            cards_row.append(col)
                        else:
                            # Render up to 3 latest published posts
                            top_posts = published_posts[:3]
                            for i, post in enumerate(top_posts):
                                col = soup.new_tag("div", **{"class": "col-lg-4 col-md-6 col-sm-12"})
                                border_class = "border-left" if i == 0 else ""
                                item_wrap = soup.new_tag("div", **{"class": f"single-blog-area-start {border_class}".strip()})

                                # Thumbnail link
                                thumb_a = soup.new_tag("a", href=f"blog-details.html?slug={post['slug']}", **{"class": "thumbnail"})
                                img = soup.new_tag("img", src=post["featured_image"], alt=post["featured_image_alt"], loading="lazy", rel="preload")
                                thumb_a.append(img)
                                item_wrap.append(thumb_a)

                                # Content area
                                inner = soup.new_tag("div", **{"class": "inner-content-area"})
                                top_area = soup.new_tag("div", **{"class": "top-area"})
                                
                                cat_span = soup.new_tag("span")
                                cat_span.string = post["category"]
                                top_area.append(cat_span)

                                title_a = soup.new_tag("a", href=f"blog-details.html?slug={post['slug']}")
                                h3 = soup.new_tag("h3", **{"class": "title"})
                                h3.string = post["title"]
                                title_a.append(h3)
                                top_area.append(title_a)

                                disc_p = soup.new_tag("p", **{"class": "disc"})
                                disc_p.string = post["excerpt"]
                                top_area.append(disc_p)

                                # Author area
                                author_div = soup.new_tag("div", **{"class": "bottom-author-area"})
                                avatar_img = soup.new_tag("img", src="assets/images/testimonials/01.png", alt="author", loading="lazy", rel="preload")
                                author_div.append(avatar_img)

                                info_div = soup.new_tag("div", **{"class": "author-area-info"})
                                h6 = soup.new_tag("h6", **{"class": "title"})
                                h6.string = post["author"]
                                info_div.append(h6)
                                role_span = soup.new_tag("span")
                                role_span.string = post["author_role"] or post["category"]
                                info_div.append(role_span)
                                author_div.append(info_div)

                                top_area.append(author_div)
                                inner.append(top_area)
                                item_wrap.append(inner)
                                col.append(item_wrap)
                                cards_row.append(col)

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        logger.info("index.html Latest Insights synchronized with %d published posts.", min(3, len(published_posts)))

    # ----------------------------------------------------
    # 3. Update sitemap.xml
    # ----------------------------------------------------
    regenerate_sitemap(published_posts)
    trigger_cloudflare_pages_deploy()
    return True

def regenerate_sitemap(published_posts=None):
    """Regenerates sitemap.xml including all verified core public pages and only published blog articles with real lastmod."""
    import xml.sax.saxutils as saxutils

    if published_posts is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT slug, updated_at, published_date FROM blog_posts WHERE status = 'published' ORDER BY published_date DESC")
        published_posts = cursor.fetchall()
        conn.close()

    base_domain = "https://codozent.com"
    core_pages = [
        ("", "index.html"),
        ("about.html", "about.html"),
        ("service.html", "service.html"),
        ("website-development.html", "website-development.html"),
        ("mobile-app-development.html", "mobile-app-development.html"),
        ("custom-software.html", "custom-software.html"),
        ("products.html", "products.html"),
        ("erp-platform.html", "erp-platform.html"),
        ("whatsapp-marketing.html", "whatsapp-marketing.html"),
        ("ai-calling-agent.html", "ai-calling-agent.html"),
        ("case-studies.html", "case-studies.html"),
        ("career.html", "career.html"),
        ("blog.html", "blog.html"),
        ("contact.html", "contact.html"),
        ("privacy-policy.html", "privacy-policy.html"),
        ("terms-of-use.html", "terms-of-use.html"),
        ("cookies-policy.html", "cookies-policy.html")
    ]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]

    # Add core public pages with real file modification dates
    for route, file_name in core_pages:
        url = f"{base_domain}/{route}" if route else f"{base_domain}/"
        file_path = os.path.join(ROOT_DIR, file_name)
        lastmod_str = None
        if os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                lastmod_str = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass

        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{url}</loc>")
        if lastmod_str:
            xml_lines.append(f"    <lastmod>{lastmod_str}</lastmod>")
        xml_lines.append("  </url>")

    # Add published blog posts only, using real publication/update dates
    for post in published_posts:
        slug = post["slug"] if isinstance(post, dict) or hasattr(post, "__getitem__") else post[0]
        if not slug or not str(slug).strip():
            continue
        safe_slug = saxutils.escape(str(slug).strip())
        url = f"{base_domain}/blog-details.html?slug={safe_slug}"

        raw_date = None
        if hasattr(post, "keys"):
            keys = post.keys()
            raw_date = post["updated_at"] if "updated_at" in keys and post["updated_at"] else (post["published_date"] if "published_date" in keys else None)
        elif isinstance(post, dict):
            raw_date = post.get("updated_at") or post.get("published_date")
        elif len(post) > 1:
            raw_date = post[1]

        lastmod_str = None
        if raw_date:
            try:
                date_str = str(raw_date)
                if "T" in date_str:
                    lastmod_str = date_str.split("T")[0]
                elif len(date_str) >= 10:
                    lastmod_str = date_str[:10]
            except Exception:
                pass

        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{url}</loc>")
        if lastmod_str:
            xml_lines.append(f"    <lastmod>{lastmod_str}</lastmod>")
        xml_lines.append("  </url>")

    xml_lines.append("</urlset>")
    sitemap_path = os.path.join(ROOT_DIR, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines) + "\n")
    logger.info("sitemap.xml regenerated: %d core pages + %d published articles.", len(core_pages), len(published_posts))

def regenerate_career_page():
    """Regenerates the public career.html with current published jobs or the honest 'No current openings' state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'published' ORDER BY id DESC")
    published_jobs = cursor.fetchall()
    conn.close()

    file_path = os.path.join(ROOT_DIR, "career.html")
    if not os.path.exists(file_path):
        logger.error("career.html not found at %s", file_path)
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    openings_area = soup.find(id="openings")
    if not openings_area:
        logger.error("Could not find #openings in career.html")
        return False

    container = openings_area.find("div", class_="container")
    if not container:
        logger.error("Could not find container inside #openings")
        return False

    rows = container.find_all("div", class_="row")
    if len(rows) < 2:
        logger.error("Unexpected row structure in #openings")
        return False

    cards_row = rows[1]
    cards_row.clear()

    if len(published_jobs) == 0:
        # Honest 'No Current Openings' empty state layout
        cards_row['class'] = ['row', 'g-5', 'mt--30', 'justify-content-center']
        col = soup.new_tag("div", **{"class": "col-lg-8 wow fadeInUp", "data-wow-delay": ".1s"})
        card = soup.new_tag("div", **{"class": "single-job-opening-card", "style": "text-align: center; padding: 50px 30px;"})
        
        icon_wrap = soup.new_tag("div", **{"style": "width: 60px; height: 60px; background: #f0f4ff; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;"})
        icon = soup.new_tag("i", **{"class": "fa-regular fa-briefcase", "style": "font-size: 24px; color: #1363DF;"})
        icon_wrap.append(icon)
        card.append(icon_wrap)

        h4 = soup.new_tag("h4", **{"class": "title", "style": "margin-bottom: 15px;"})
        h4.string = "No Current Openings"
        card.append(h4)

        p1 = soup.new_tag("p", **{"style": "font-size: 15px; color: #555; line-height: 1.7; max-width: 600px; margin: 0 auto 25px;"})
        p1.string = "There are currently no active open positions at Codozent Technologies. However, we are always eager to connect with talented frontend engineers, cross-platform mobile developers, and backend software architects who value clean code and dependable execution."
        card.append(p1)

        p2 = soup.new_tag("p", **{"style": "font-size: 14px; color: #777;"})
        p2.string = "If you would like to be considered for future openings, feel free to share your resume and GitHub profile with us directly:"
        card.append(p2)

        cta_wrap = soup.new_tag("div", **{"style": "margin-top: 25px;"})
        a = soup.new_tag("a", href="mailto:codozent.help@gmail.com", **{"class": "rts-btn btn-primary btn-bold"})
        a.string = "Email codozent.help@gmail.com"
        cta_wrap.append(a)
        card.append(cta_wrap)

        col.append(card)
        cards_row.append(col)
    else:
        # Published jobs grid
        cards_row['class'] = ['row', 'g-5', 'mt--30']
        for job in published_jobs:
            col = soup.new_tag("div", **{"class": "col-lg-6 col-md-12"})
            card = soup.new_tag("div", **{
                "class": "single-job-opening-card",
                "style": "padding: 35px 30px; border: 1px solid #D8E5F8; border-radius: 12px; background: #ffffff; height: 100%; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 4px 20px rgba(0,0,0,0.03);"
            })

            top_div = soup.new_tag("div")

            # Title
            h4 = soup.new_tag("h4", **{"class": "title", "style": "margin-bottom: 8px; font-size: 20px;"})
            h4.string = job["title"]
            top_div.append(h4)

            # Metadata tags
            meta_div = soup.new_tag("div", **{
                "style": "display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; font-size: 13px; color: #1363DF; font-weight: 500;"
            })

            dept_span = soup.new_tag("span")
            dept_icon = soup.new_tag("i", **{"class": "fa-regular fa-briefcase", "style": "margin-right: 4px;"})
            dept_span.append(dept_icon)
            dept_span.append(f" {job['department']}")
            meta_div.append(dept_span)

            loc_span = soup.new_tag("span")
            loc_icon = soup.new_tag("i", **{"class": "fa-regular fa-location-dot", "style": "margin-right: 4px;"})
            loc_span.append(loc_icon)
            loc_span.append(f" {job['location']}")
            meta_div.append(loc_span)

            type_span = soup.new_tag("span")
            type_icon = soup.new_tag("i", **{"class": "fa-regular fa-clock", "style": "margin-right: 4px;"})
            type_span.append(type_icon)
            type_span.append(f" {job['employment_type']}")
            meta_div.append(type_span)

            top_div.append(meta_div)

            # Description
            desc_p = soup.new_tag("p", **{"style": "font-size: 14px; color: #555; line-height: 1.6; margin-bottom: 15px;"})
            desc_p.string = job["description"]
            top_div.append(desc_p)

            # Requirements preview if present
            if job["qualifications"]:
                req_div = soup.new_tag("div", **{"style": "font-size: 13px; color: #666; margin-bottom: 20px; line-height: 1.5;"})
                req_title = soup.new_tag("strong", **{"style": "color: #0D1D3E; display: block; margin-bottom: 4px;"})
                req_title.string = "Qualifications:"
                req_div.append(req_title)
                req_div.append(job["qualifications"][:180] + ("..." if len(job["qualifications"]) > 180 else ""))
                top_div.append(req_div)

            card.append(top_div)

            # Bottom Apply Button
            bot_div = soup.new_tag("div", **{"style": "margin-top: 15px; display: flex; align-items: center; justify-content: space-between;"})
            
            apply_btn = soup.new_tag("a", href=job["apply_url"], target="_blank", rel="noopener noreferrer", **{"class": "rts-btn btn-primary btn-bold", "style": "padding: 10px 22px; font-size: 14px;"})
            apply_btn.string = job["apply_label"] or "Apply for Role"
            arrow = soup.new_tag("i", **{"class": "fa-regular fa-arrow-up-right", "style": "margin-left: 6px;"})
            apply_btn.append(arrow)
            bot_div.append(apply_btn)

            if job["deadline"]:
                deadline_span = soup.new_tag("span", **{"style": "font-size: 12px; color: #888;"})
                deadline_span.string = f"Deadline: {job['deadline']}"
                bot_div.append(deadline_span)

            card.append(bot_div)
            col.append(card)
            cards_row.append(col)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    regenerate_sitemap()
    logger.info("career.html successfully regenerated. Published jobs: %d", len(published_jobs))
    trigger_cloudflare_pages_deploy()
    return True

def publish_homepage_images():
    """Publishes draft homepage images to index.html with strict preservation of containers and dimensions."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM homepage_images")
    slots = cursor.fetchall()

    file_path = os.path.join(ROOT_DIR, "index.html")
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    updated_count = 0
    for slot in slots:
        new_src = (slot["draft_src"] or slot["current_src"] or "").strip()
        if new_src.startswith("res.cloudinary.com"):
            new_src = f"https://{new_src}"

        new_alt = (slot["draft_alt"] or slot["current_alt"] or "").strip()

        found_img = None
        # 1. Try selector if available
        selector = slot.get("selector")
        if selector:
            try:
                found_img = soup.select_one(selector)
            except Exception:
                found_img = None

        # 2. Fallback to searching by src
        if not found_img:
            for img in soup.find_all("img"):
                cur_img_src = img.get("src", "").strip()
                if (cur_img_src == slot["current_src"] or 
                    (slot["draft_src"] and cur_img_src == slot["draft_src"]) or 
                    (slot["current_src"] and cur_img_src.endswith(slot["current_src"]))):
                    found_img = img
                    break

        if found_img:
            found_img["src"] = new_src
            found_img["alt"] = new_alt
            style = found_img.get("style", "")
            if "object-fit" not in style:
                found_img["style"] = (style + "; object-fit: cover;").strip("; ")
            updated_count += 1

        # Keep video_section in sync if it's the video thumbnail
        if slot["slot_key"] == "video_thumbnail":
            cursor.execute(
                "UPDATE homepage_video_section SET image_url = ?, image_alt = ? WHERE id = 1",
                (new_src, new_alt)
            )

        cursor.execute(
            """
            UPDATE homepage_images
            SET current_src = ?, current_alt = ?, has_draft = 0, updated_at = ?
            WHERE slot_key = ?
            """,
            (new_src, new_alt, datetime.now(timezone.utc).isoformat(), slot["slot_key"])
        )

    conn.commit()
    conn.close()

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info("Homepage images published successfully (%d updated).", updated_count)
    trigger_cloudflare_pages_deploy()
    return True

def publish_page_text(page_key: str):
    """Publishes draft text fields for a given page to its static HTML file."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE page_key = ?", (page_key,))
    page = cursor.fetchone()
    if not page:
        conn.close()
        return False, "Page not found"

    fields = json.loads(page["fields_json"])
    file_path = os.path.join(ROOT_DIR, page["file_name"])
    if not os.path.exists(file_path):
        conn.close()
        return False, f"File {page['file_name']} does not exist"

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # Update metadata
    if page["meta_title"]:
        title_tag = soup.find("title")
        if title_tag:
            title_tag.string = page["meta_title"]
        else:
            new_title = soup.new_tag("title")
            new_title.string = page["meta_title"]
            if soup.head:
                soup.head.append(new_title)

    if page["meta_description"]:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            meta_desc["content"] = page["meta_description"]
        elif soup.head:
            new_meta = soup.new_tag("meta", attrs={"name": "description", "content": page["meta_description"]})
            soup.head.append(new_meta)

    # Update page-specific fields
    if page_key == "index":
        badge = soup.find("span", class_="pre-title")
        if badge and "hero_badge" in fields:
            badge.string = fields["hero_badge"]["draft_value"]

        title_h1 = soup.find("h1", class_="title")
        if title_h1 and "hero_title" in fields:
            val = fields["hero_title"]["draft_value"]
            if "Growing" in val:
                parts = val.split("Growing", 1)
                title_h1.clear()
                title_h1.append(parts[0])
                span = soup.new_tag("span")
                span.string = "Growing"
                title_h1.append(span)
                title_h1.append(parts[1])
            else:
                title_h1.string = val

        banner_wrap = soup.find("div", class_="banner-wrapper-one")
        if banner_wrap and "hero_desc" in fields:
            desc_p = banner_wrap.find("p")
            if desc_p:
                desc_p.string = fields["hero_desc"]["draft_value"]

        if banner_wrap and "hero_cta_text" in fields:
            cta_btn = banner_wrap.find("a", class_="rts-btn")
            if cta_btn:
                icon_img = cta_btn.find("img")
                cta_btn.clear()
                cta_btn.string = fields["hero_cta_text"]["draft_value"] + " "
                if icon_img:
                    cta_btn.append(icon_img)

        video_wrap = soup.find("div", class_="title-video-top")
        if video_wrap:
            if "video_title_1" in fields:
                p_large = video_wrap.find("p", class_="large")
                if p_large:
                    val = fields["video_title_1"]["draft_value"]
                    p_large.clear()
                    if "clean, stable" in val and "accelerate" in val:
                        part1, rest = val.split("clean, stable", 1)
                        part2, part3 = rest.split("accelerate", 1)
                        p_large.append(part1)
                        s1 = soup.new_tag("span")
                        s1.string = "clean, stable"
                        p_large.append(s1)
                        p_large.append(part2)
                        s2 = soup.new_tag("span")
                        s2.string = "accelerate"
                        p_large.append(s2)
                        p_large.append(part3)
                    else:
                        p_large.string = val

            if "video_desc" in fields:
                p_disc = video_wrap.find("p", class_="disc")
                if p_disc:
                    p_disc.string = fields["video_desc"]["draft_value"]

    elif page_key == "about":
        hero_title = soup.find("h1", class_="title")
        if hero_title and "hero_title" in fields:
            hero_title.string = fields["hero_title"]["draft_value"]

    # Mark drafts as current in DB
    now_str = datetime.now(timezone.utc).isoformat()
    for k, v in fields.items():
        v["current_value"] = v["draft_value"]

    cursor.execute(
        """
        UPDATE pages
        SET fields_json = ?, has_draft = 0, updated_at = ?, published_at = ?
        WHERE page_key = ?
        """,
        (json.dumps(fields), now_str, now_str, page_key)
    )
    conn.commit()
    conn.close()

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info("Page %s published successfully to %s", page_key, file_path)
    return True, "Published successfully"

def regenerate_work_section():
    """
    CRITICAL SYNCHRONIZATION FUNCTION:
    Synchronizes published work items into:
    1. index.html ("Featured Engineering Work" section)
    2. case-studies.html (Dedicated technical approach cards)
    Strictly preserves card classes, image dimensions, aspect ratios, and responsiveness.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM work_items WHERE status = 'published' ORDER BY display_order ASC, id ASC")
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # 1. Update index.html
    index_file = os.path.join(ROOT_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Find "Featured Engineering Work" heading
        feat_heading = None
        for h2 in soup.find_all("h2"):
            if "Featured Engineering Work" in h2.get_text():
                feat_heading = h2
                break

        if feat_heading:
            parent_container = feat_heading.find_parent("div", class_="container")
            if parent_container:
                card_row = parent_container.find("div", class_="g-80")
                if card_row:
                    card_row.clear()
                    for idx, item in enumerate(items):
                        delay = f".{ (idx % 2) * 2 }s" if (idx % 2) != 0 else None
                        col_div = soup.new_tag("div", **{"class": "col-lg-6 col-md-6 col-sm-12 wow fadeInUp", "data-wow-offset": "120"})
                        if delay:
                            col_div["data-wow-delay"] = delay

                        card_div = soup.new_tag("div", **{"class": "single-case-studies"})
                        target_url = item["project_url"] or "case-studies.html"

                        thumb_a = soup.new_tag("a", href=target_url, **{"class": "thumbnail"})
                        raw_url = (item["image_url"] or "").strip()
                        img_src = f"https://{raw_url}" if raw_url.startswith("res.cloudinary.com") else raw_url
                        img_tag = soup.new_tag(
                            "img",
                            src=img_src,
                            alt=item["image_alt"],
                            loading="lazy",
                            style="width: 100%; height: 100%; object-fit: cover;"
                        )
                        thumb_a.append(img_tag)
                        card_div.append(thumb_a)

                        inner_div = soup.new_tag("div", **{"class": "inner-content"})
                        span_cat = soup.new_tag("span")
                        span_cat.string = item["category"]
                        inner_div.append(span_cat)

                        title_a = soup.new_tag("a", href=target_url)
                        h3_title = soup.new_tag("h3", **{"class": "title"})
                        h3_title.string = item["title"]
                        title_a.append(h3_title)
                        inner_div.append(title_a)

                        btn_a = soup.new_tag("a", href=target_url, **{"class": "rts-btn btn-border"})
                        btn_a.string = "View Technical Approach "
                        arrow_img = soup.new_tag("img", src="assets/images/service/icons/13.svg", alt="arrow", **{"class": "injectable"})
                        btn_a.append(arrow_img)
                        inner_div.append(btn_a)

                        card_div.append(inner_div)
                        col_div.append(card_div)
                        card_row.append(col_div)

                    with open(index_file, "w", encoding="utf-8") as f:
                        f.write(str(soup))
                    logger.info("index.html Featured Engineering Work synchronized with %d items.", len(items))

    # 2. Update case-studies.html
    cs_file = os.path.join(ROOT_DIR, "case-studies.html")
    if os.path.exists(cs_file):
        with open(cs_file, "r", encoding="utf-8") as f:
            cs_soup = BeautifulSoup(f.read(), "html.parser")

        cs_row = cs_soup.find("div", class_="g-80")
        if cs_row:
            cs_row.clear()
            for idx, item in enumerate(items):
                col_div = cs_soup.new_tag("div", **{"class": "col-lg-6 col-md-6 col-sm-12 wow fadeInUp", "data-wow-offset": "120"})
                card_div = cs_soup.new_tag("div", **{"class": "single-case-studies"})
                target_url = item["project_url"] or "case-studies.html"

                thumb_div = cs_soup.new_tag("div", **{"class": "thumbnail"})
                raw_url = (item["image_url"] or "").strip()
                img_src = f"https://{raw_url}" if raw_url.startswith("res.cloudinary.com") else raw_url
                img_tag = cs_soup.new_tag(
                    "img",
                    src=img_src,
                    alt=item["image_alt"],
                    loading="lazy",
                    style="width: 100%; height: 100%; object-fit: cover;"
                )
                thumb_div.append(img_tag)
                card_div.append(thumb_div)

                inner_div = cs_soup.new_tag("div", **{"class": "inner-content"})
                span_cat = cs_soup.new_tag("span")
                span_cat.string = item["category"]
                inner_div.append(span_cat)

                h3_title = cs_soup.new_tag("h3", **{"class": "title"})
                h3_title.string = item["title"]
                inner_div.append(h3_title)

                if item["description"]:
                    p_desc = cs_soup.new_tag("p", style="font-size: 14px; color: #666; line-height: 1.6; margin-top: 10px;")
                    p_desc.string = item["description"]
                    inner_div.append(p_desc)

                card_div.append(inner_div)
                col_div.append(card_div)
                cs_row.append(col_div)

            with open(cs_file, "w", encoding="utf-8") as f:
                f.write(str(cs_soup))
            logger.info("case-studies.html synchronized with %d items.", len(items))

    trigger_cloudflare_pages_deploy()
    return True

def sync_homepage_video_section(video_enabled: bool, video_url: str, image_url: str = None, image_alt: str = None):
    """
    Synchronizes the video showcase section in index.html:
    - When video_enabled is True:
        Ensures <div class="vedio-icone"> exists inside <div class="image--large-video"> with <a class="popup-video"> pointing to video_url.
    - When video_enabled is False:
        Removes <div class="vedio-icone"> completely so ONLY the static image is displayed and no video icon appears.
    - Updates <img class="jarallax-img"> src and alt attributes.
    """
    index_file = os.path.join(ROOT_DIR, "index.html")
    if not os.path.exists(index_file):
        logger.warning("index.html not found at %s", index_file)
        return False

    with open(index_file, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    container = soup.find("div", class_="image--large-video")
    if not container:
        logger.warning("Could not find .image--large-video container in index.html")
        return False

    # 1. Update image src and alt
    if image_url:
        clean_img_url = image_url.strip()
        if clean_img_url.startswith("res.cloudinary.com"):
            clean_img_url = f"https://{clean_img_url}"
        img = container.find("img", class_="jarallax-img") or container.find("img")
        if img:
            img["src"] = clean_img_url
            if image_alt:
                img["alt"] = image_alt.strip()

    # 2. Update video icon according to toggle
    icon_div = container.find("div", class_="vedio-icone")
    if video_enabled:
        clean_vid_url = (video_url or "https://www.youtube.com/watch?v=vZE0j_WCRvI").strip()
        if not icon_div:
            icon_div = soup.new_tag("div", **{"class": "vedio-icone"})
            play_a = soup.new_tag("a", href=clean_vid_url, **{"class": "video-play-button play-video popup-video"})
            play_span = soup.new_tag("span")
            play_a.append(play_span)
            icon_div.append(play_a)

            overlay_div = soup.new_tag("div", **{"class": "video-overlay"})
            close_a = soup.new_tag("a", href="#section1", **{"class": "video-overlay-close"})
            close_a.string = "×"
            overlay_div.append(close_a)
            icon_div.append(overlay_div)

            container.append(icon_div)
        else:
            play_a = icon_div.find("a", class_="popup-video") or icon_div.find("a")
            if play_a:
                play_a["href"] = clean_vid_url
    else:
        # Video disabled: Image only mode, remove video icon completely
        if icon_div:
            icon_div.decompose()

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(str(soup))

    logger.info("index.html video section synchronized (video_enabled=%s, video_url=%s)", video_enabled, video_url)
    trigger_cloudflare_pages_deploy()
    return True

if __name__ == '__main__':
    from cms.db import init_db
    init_db()
    seed_content()
    regenerate_blog_page()
    regenerate_career_page()
