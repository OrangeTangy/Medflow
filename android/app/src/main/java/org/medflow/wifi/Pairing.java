package org.medflow.wifi;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class Pairing {
    static JSONObject read(Context context) throws Exception {
        return validate(context.getSharedPreferences("pairing", 0).getString("config", ""));
    }

    static JSONObject validate(String text) throws Exception {
        JSONObject config = new JSONObject(text);
        if (config.getInt("version") != 1) throw new Exception("Unsupported pairing version");
        UUID.fromString(config.getString("device_id"));
        String token = config.getString("token"), ssid = config.getString("ssid");
        if (!token.matches("[a-zA-Z0-9_-]{40,100}")) throw new Exception("Invalid device token");
        if (ssid.isEmpty() || ssid.getBytes(StandardCharsets.UTF_8).length > 32) throw new Exception("Invalid WiFi name");
        String urlText = config.getString("receiver_url").replaceAll("/+$", "");
        URI url = new URI(urlText);
        if (url.getHost() == null || url.getUserInfo() != null || url.getQuery() != null || url.getFragment() != null || (url.getPath() != null && !url.getPath().isEmpty())) throw new Exception("Use a receiver base URL without paths");
        boolean privateHttp = false;
        String host = url.getHost();
        if (host.equals("localhost") || host.equals("127.0.0.1")) privateHttp = true;
        if (host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+")) {
            String[] parts = host.split("\\.");
            int a = Integer.parseInt(parts[0]), b = Integer.parseInt(parts[1]);
            for (String part : parts) if (Integer.parseInt(part) > 255) throw new Exception("Invalid receiver IP");
            privateHttp = a == 10 || a == 127 || (a == 192 && b == 168) || (a == 172 && b >= 16 && b <= 31);
        }
        if (!"https".equals(url.getScheme()) && !("http".equals(url.getScheme()) && privateHttp)) throw new Exception("Use HTTPS, or a private IPv4 address for a LAN-only test");
        config.put("receiver_url", urlText);
        return config;
    }

    @android.annotation.SuppressLint("ApplySharedPref")
    static void save(Context context, JSONObject config) {
        // Persist the pairing before allowing the monitoring service to start.
        context.getSharedPreferences("pairing", 0).edit().putString("config", config.toString()).commit();
    }
}
