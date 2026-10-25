package org.medflow.wifi;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONObject;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

final class EventStore extends SQLiteOpenHelper {
    EventStore(Context context) { super(context, "wifi-events.sqlite3", null, 2); }
    @Override public void onConfigure(SQLiteDatabase db) { db.enableWriteAheadLogging(); }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,device_id TEXT NOT NULL,payload TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0,error TEXT)");
        db.execSQL("CREATE INDEX events_pending ON events(device_id,sent,sequence)");
    }
    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        if (oldVersion < 2) db.execSQL("ALTER TABLE events ADD COLUMN error TEXT");
    }

    synchronized void append(String device, String kind, String ssid, boolean initial, String note) throws Exception {
        JSONObject event = new JSONObject();
        String id = UUID.randomUUID().toString();
        event.put("id", id).put("event_type", kind).put("observed_at", Instant.now().toString()).put("initial_observation", initial);
        if (ssid != null) event.put("ssid", ssid);
        if (note != null) event.put("note", note);
        ContentValues values = new ContentValues();
        values.put("id", id); values.put("device_id", device); values.put("payload", event.toString());
        getWritableDatabase().insertOrThrow("events", null, values); // Disk first, then network.
        getWritableDatabase().execSQL("DELETE FROM events WHERE sent=1 AND sequence < COALESCE((SELECT sequence FROM events ORDER BY sequence DESC LIMIT 1 OFFSET 999),0)");
    }

    synchronized List<JSONObject> pending(String device) throws Exception {
        List<JSONObject> result = new ArrayList<>();
        try (Cursor rows = getReadableDatabase().rawQuery("SELECT payload FROM events WHERE device_id=? AND sent=0 ORDER BY sequence LIMIT 50", new String[]{device})) {
            while (rows.moveToNext()) result.add(new JSONObject(rows.getString(0)));
        }
        return result;
    }
    synchronized void acknowledge(String id) {
        ContentValues values = new ContentValues(); values.put("sent", 1);
        getWritableDatabase().update("events", values, "id=?", new String[]{id});
    }
    synchronized void reject(String id, int code) {
        ContentValues values = new ContentValues(); values.put("sent",2); values.put("error","HTTP "+code);
        getWritableDatabase().update("events",values,"id=?",new String[]{id});
    }
    synchronized String display() {
        StringBuilder result = new StringBuilder();
        try (Cursor rows = getReadableDatabase().rawQuery("SELECT payload,sent FROM events ORDER BY sequence DESC LIMIT 30", null)) {
            while (rows.moveToNext()) {
                try {
                    JSONObject row = new JSONObject(rows.getString(0));
                    result.append(row.getString("observed_at")).append("\n").append(row.getString("event_type"));
                    if (row.optBoolean("initial_observation")) result.append(" (initial observation)");
                    result.append(rows.getInt(1) == 1 ? " · delivered\n\n" : rows.getInt(1) == 2 ? " · rejected, retained for review\n\n" : " · queued offline\n\n");
                } catch (Exception ignored) { }
            }
        }
        return result.length() == 0 ? "No WiFi observations yet." : result.toString();
    }
}
