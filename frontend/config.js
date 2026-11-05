// Base da API.
// - Servido pelo próprio FastAPI em /app/  → mesma origem, sem prefixo.
// - Servido pela Netlify (raiz)            → /api/*, que a Netlify repassa ao backend no Fly (netlify.toml).
window.ESCUTA_API = window.ESCUTA_API ?? (location.pathname.startsWith("/app/") ? "" : "/api");
