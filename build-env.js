const fs = require('fs');

const envData = {};
['ADMIN_EMAIL', 'ADMIN_PASSWORD', 'CMS_SECRET_KEY', 'SUPABASE_KEY', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_ANON_KEY'].forEach(key => {
    if (process.env[key]) {
        envData[key] = process.env[key];
    }
});

fs.writeFileSync('_env_generated.js', `export default ${JSON.stringify(envData)};\n`);
console.log('✅ Generated _env_generated.js with keys:', Object.keys(envData));
