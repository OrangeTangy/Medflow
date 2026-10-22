import { api } from "./api.mjs";
import { assets } from "./assets.mjs";
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    let response;
    if (path.startsWith("/api/")) response = await api(request, env);
    else {
      const asset =
        assets[path] ||
        assets[path + "/index.html"] ||
        (path === "/" ? assets["/index.html"] : undefined);
      if (!asset) response = new Response("Not found", { status: 404 });
      else
        response = new Response(
          Uint8Array.from(atob(asset.body), (c) => c.charCodeAt(0)),
          {
            headers: {
              "Content-Type": asset.type,
              "Cache-Control": path.startsWith("/_next/")
                ? "public, max-age=31536000, immutable"
                : "no-cache",
            },
          },
        );
    }
    response.headers.set("X-Content-Type-Options", "nosniff");
    response.headers.set("Referrer-Policy", "same-origin");
    response.headers.set(
      "Strict-Transport-Security",
      "max-age=31536000; includeSubDomains",
    );
    response.headers.set("Permissions-Policy", "camera=(), geolocation=()");
    response.headers.set("X-Frame-Options", "SAMEORIGIN");
    response.headers.set(
      "Content-Security-Policy",
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'",
    );
    return response;
  },
};
