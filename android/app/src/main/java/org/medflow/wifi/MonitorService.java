package org.medflow.wifi;

import android.Manifest;
import android.app.*;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.LocationManager;
import android.net.*;
import android.net.wifi.*;
import android.os.*;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class MonitorService extends Service {
    private ScheduledExecutorService worker;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback callback;
    private EventStore store;
    private JSONObject pairing;
    private String previous = null;
    private String previousError = null;
    private long lastTick = 0;
    private int ticks = 0;

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("monitor", "WiFi monitoring", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, MonitorService.class).setAction("STOP");
        PendingIntent stopAction = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, "monitor").setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("Medflow WiFi monitoring").setContentText("Logging the selected WiFi. Tap to see events.")
            .setContentIntent(open).addAction(new Notification.Action.Builder(null,"Stop",stopAction).build()).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE | ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        else if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        else startForeground(1,notification);
        store = new EventStore(this);
        try { pairing = Pairing.read(this); }
        catch (Exception e) { status("Save a pairing before starting monitoring."); stopSelf(); return; }
        worker = Executors.newSingleThreadScheduledExecutor();
        try { store.append(pairing.getString("device_id"),"monitor_started",null,false,"User started monitoring; no earlier connectivity inferred."); }
        catch (Exception e) { status("Cannot save the event log. Monitoring stopped."); stopSelf(); return; }
        connectivity = getSystemService(ConnectivityManager.class);
        callback = new ConnectivityManager.NetworkCallback() {
            private void update() { if (worker != null && !worker.isShutdown()) worker.execute(() -> observe()); }
            @Override public void onAvailable(Network network) { update(); }
            @Override public void onLost(Network network) { update(); }
            @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) { update(); }
        };
        try { connectivity.registerNetworkCallback(new NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build(),callback); }
        catch (Exception e) { status("WiFi callbacks unavailable; using periodic observations."); }
        worker.scheduleWithFixedDelay(() -> {
            try {
                long tick = SystemClock.elapsedRealtime();
                if (lastTick > 0 && tick-lastTick > 30000) { previous=null; emit("unknown",false,"Observer gap; connectivity during sleep is unknown."); }
                lastTick=tick;
                observe();
                if (ticks++ % 3 == 0) flush();
            } catch (Exception e) { status("Local monitoring error: " + e.getClass().getSimpleName()); }
        }, 0, 3, TimeUnit.SECONDS);
    }

    private void observe() {
        try {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) throw new Exception("Precise location permission is required");
            LocationManager location = getSystemService(LocationManager.class);
            if (Build.VERSION.SDK_INT >= 28 && !location.isLocationEnabled()) throw new Exception("Turn on Android Location services to read the selected WiFi");
            boolean wifi = false;
            for (Network network : connectivity.getAllNetworks()) {
                NetworkCapabilities caps = connectivity.getNetworkCapabilities(network);
                if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) wifi=true;
            }
            String state="disconnected";
            if (wifi) {
                WifiManager manager=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);
                WifiInfo info=manager.getConnectionInfo();
                String ssid=info == null ? null : info.getSSID();
                if (ssid == null || ssid.equals(WifiManager.UNKNOWN_SSID) || info.getNetworkId() == -1) throw new Exception("WiFi name is unavailable; check permissions. No departure inferred");
                if (ssid.startsWith("\"") && ssid.endsWith("\"")) ssid=ssid.substring(1,ssid.length()-1);
                state=ssid.equals(pairing.getString("ssid")) ? "connected" : "disconnected";
            }
            boolean initial=previous == null;
            if (!state.equals(previous)) emit(state,initial,initial ? "Initial observed state; no arrival/departure before this instant inferred." : null);
            previous=state; previousError=null;
        } catch (Exception e) {
            String error=e.getMessage();
            if (!String.valueOf(error).equals(previousError)) { emit("unknown",false,error); previousError=error; }
            previous=null;
            status("WiFi state unknown: " + error);
        }
    }
    private void emit(String kind, boolean initial, String note) {
        try { store.append(pairing.getString("device_id"),kind,kind.equals("connected")||kind.equals("disconnected") ? pairing.getString("ssid") : null,initial,note); }
        catch (Exception e) { status("Unable to save local event. Check available storage."); }
    }
    private void flush() {
        try {
            for (JSONObject event : store.pending(pairing.getString("device_id"))) {
                HttpURLConnection connection=(HttpURLConnection)new URL(pairing.getString("receiver_url")+"/api/events").openConnection();
                try {
                    connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(4000); connection.setReadTimeout(4000);
                    connection.setRequestMethod("POST"); connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type","application/json");
                    connection.setRequestProperty("Authorization","Bearer "+pairing.getString("token"));
                    byte[] bytes=event.toString().getBytes(StandardCharsets.UTF_8);
                    connection.setFixedLengthStreamingMode(bytes.length);
                    try (java.io.OutputStream out=connection.getOutputStream()) { out.write(bytes); }
                    int code=connection.getResponseCode();
                    if (code == 409 || code == 422) { store.reject(event.getString("id"),code); continue; }
                    if (code != 200) { status("Receiver returned " + code + ". Events stay queued; check pairing, phone clock, or receiver address."); return; }
                    try (java.io.InputStream input=connection.getInputStream()) {
                        java.io.ByteArrayOutputStream received=new java.io.ByteArrayOutputStream();
                        byte[] buffer=new byte[1024]; int count;
                        while ((count=input.read(buffer)) != -1) { if (received.size()+count > 4096) throw new Exception("Oversized acknowledgement"); received.write(buffer,0,count); }
                        String response=new String(received.toByteArray(),StandardCharsets.UTF_8);
                        if (!new JSONObject(response).getString("id").equals(event.getString("id"))) throw new Exception("Invalid receiver acknowledgement");
                    }
                    store.acknowledge(event.getString("id"));
                } finally { connection.disconnect(); }
            }
            status("Monitoring " + pairing.getString("ssid") + " · " + (previous == null ? "state unknown" : previous) + " · receiver reached. Device signals are unverified.");
        } catch (Exception e) { status("Monitoring locally · receiver unreachable. Events are queued and will retry when connectivity returns."); }
    }
    private void status(String value) { getSharedPreferences("monitor",0).edit().putString("status",value).apply(); }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        return START_STICKY;
    }
    @Override public void onDestroy() {
        if (connectivity != null && callback != null) try { connectivity.unregisterNetworkCallback(callback); } catch (Exception ignored) { }
        if (worker != null) worker.shutdownNow();
        // Stopping the observer is not a WiFi disconnection. Resume to send queued data.
        if (store != null) { emit("monitor_stopped",false,"Monitoring stopped; later connectivity is unknown."); store.close(); }
        status("Monitoring stopped. Queued observations remain on the phone.");
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
