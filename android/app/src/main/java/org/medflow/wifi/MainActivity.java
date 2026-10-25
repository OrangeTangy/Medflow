package org.medflow.wifi;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;
import java.util.ArrayList;

public class MainActivity extends Activity {
    private EditText config;
    private TextView status, logs;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private EventStore store;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            logs.setText(store.display());
            status.setText(getSharedPreferences("monitor", 0).getString("status", "Monitoring is stopped."));
            ui.postDelayed(this, 2000);
        }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new EventStore(this);
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(22 * getResources().getDisplayMetrics().density);
        body.setPadding(pad,pad,pad,pad); body.setBackgroundColor(Color.rgb(245,249,249)); scroll.addView(body);
        TextView title = text(body, "Medflow WiFi", 28);
        title.setTextColor(Color.rgb(8,127,117));
        text(body, "Monitor your selected WiFi and notify your paired main computer. Device signals are unverified presence evidence. No WiFi password is needed.", 15);
        text(body, "Private pairing configuration", 18);
        config = new EditText(this); config.setMinLines(6); config.setGravity(android.view.Gravity.TOP);
        config.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        config.setHint("Paste pairing JSON from the main computer"); body.addView(config);
        text(body, "Pairing tokens stay private on this phone. HTTP is allowed only for a private LAN test and is unencrypted. Use HTTPS for deployment.", 13);
        button(body, "Save pairing", v -> {
            try {
                JSONObject next = Pairing.validate(config.getText().toString());
                stopService(new Intent(this, MonitorService.class));
                Pairing.save(this, next); config.setText("");
                Toast.makeText(this, "Paired to WiFi: " + next.getString("ssid") + ". Start monitoring below.", Toast.LENGTH_LONG).show();
            } catch (Exception e) { Toast.makeText(this, e.getMessage(), Toast.LENGTH_LONG).show(); }
        });
        button(body, "Allow WiFi permissions", v -> permissions());
        button(body, "Open location settings", v -> startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)));
        text(body, "Android requires precise location permission and Location services to reveal a WiFi name. Start monitoring with this screen visible. A persistent notification lets you stop it. Battery restrictions, force-stop, and reboot can interrupt monitoring.", 13);
        button(body, "Start monitoring", v -> {
            try {
                Pairing.read(this);
                if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) { permissions(); return; }
                android.location.LocationManager location=getSystemService(android.location.LocationManager.class);
                if (Build.VERSION.SDK_INT >= 28 && !location.isLocationEnabled()) { Toast.makeText(this,"Turn on Location services first.",Toast.LENGTH_LONG).show(); return; }
                startForegroundService(new Intent(this, MonitorService.class));
            } catch (Exception e) { Toast.makeText(this, "Save a valid pairing first: " + e.getMessage(), Toast.LENGTH_LONG).show(); }
        });
        button(body, "Stop monitoring", v -> {
            stopService(new Intent(this, MonitorService.class));
            getSharedPreferences("monitor",0).edit().putString("status","Monitoring is stopped. Unsent observations stay on this phone until monitoring resumes.").apply();
        });
        status = text(body,"",15);
        text(body,"Local event log (UTC)",20);
        logs = text(body,"",14); logs.setTextIsSelectable(true);
        setContentView(scroll);
    }
    private TextView text(LinearLayout body, String value, int size) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setPadding(0,14,0,14); body.addView(view); return view;
    }
    private void button(LinearLayout body, String label, View.OnClickListener listener) {
        Button button = new Button(this); button.setText(label); button.setOnClickListener(listener); body.addView(button);
    }
    private void permissions() {
        ArrayList<String> requested = new ArrayList<>();
        requested.add(Manifest.permission.ACCESS_COARSE_LOCATION); requested.add(Manifest.permission.ACCESS_FINE_LOCATION);
        if (Build.VERSION.SDK_INT >= 33) { requested.add(Manifest.permission.NEARBY_WIFI_DEVICES); requested.add(Manifest.permission.POST_NOTIFICATIONS); }
        requestPermissions(requested.toArray(new String[0]), 1);
    }
    @Override protected void onResume() { super.onResume(); ui.post(refresh); }
    @Override protected void onPause() { ui.removeCallbacks(refresh); super.onPause(); }
    @Override protected void onDestroy() { store.close(); super.onDestroy(); }
}
