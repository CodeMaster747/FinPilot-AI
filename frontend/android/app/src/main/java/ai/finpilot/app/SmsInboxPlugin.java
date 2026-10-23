package ai.finpilot.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.provider.Telephony;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

/**
 * Reads the phone's SMS inbox for FinPilot. Filtering happens here, on the phone: messages from personal numbers,
 * promotional (-P) senders and one-time passwords never reach the app's web layer or the network.
 */
@CapacitorPlugin(name = "SmsInbox", permissions = { @Permission(alias = "sms", strings = { Manifest.permission.READ_SMS }) })
public class SmsInboxPlugin extends Plugin {

    /** A business sender ID: an optional operator prefix, six letters/digits, an optional route suffix (VM-HDFCBK-S). */
    private static final Pattern HEADER = Pattern.compile("^(?:[A-Z]{2}-)?[A-Z0-9]{6}(?:-[PSTG])?$");
    private static final Pattern PROMO = Pattern.compile("^(?:[A-Z]{2}-)?[A-Z0-9]{6}-P$");
    private static final Pattern OTP = Pattern.compile("(?i)\\b(otp|one[- ]time password|verification code)\\b");
    // a completed money movement: a real alert may end with "never share your OTP" and must still be kept
    private static final Pattern MOVED = Pattern.compile(
            "(?i)\\b(debited|credited|deposited|withdrawn|spent|sent|paid|received|transferred)\\b");

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private static boolean hasLetter(String s) {
        for (int i = 0; i < s.length(); i++) {
            if (Character.isLetter(s.charAt(i))) return true;
        }
        return false;
    }

    /** "business" | "personal" | "promo" — only business senders are ever read. */
    static String senderKind(String address) {
        String a = address == null ? "" : address.trim().toUpperCase();
        if (a.isEmpty() || !hasLetter(a)) return "personal";
        if (PROMO.matcher(a).matches()) return "promo";
        return "business";
    }

    static boolean isOtpOnly(String body) {
        return OTP.matcher(body).find() && !MOVED.matcher(body).find();
    }

    private JSObject device() {
        JSObject d = new JSObject();
        d.put("manufacturer", Build.MANUFACTURER);
        d.put("model", Build.MODEL);
        d.put("sdk", Build.VERSION.SDK_INT);
        try {
            PackageInfo info = getContext().getPackageManager().getPackageInfo(getContext().getPackageName(), 0);
            d.put("app_version", info.versionName);
        } catch (Exception ignored) {
            d.put("app_version", "");
        }
        return d;
    }

    private JSObject status() {
        JSObject ret = new JSObject();
        PermissionState state = getPermissionState("sms");
        ret.put("permission", state == null ? "prompt" : state.toString());
        ret.put("device", device());
        return ret;
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        call.resolve(status());
    }

    @PluginMethod
    public void requestAccess(PluginCall call) {
        if (getPermissionState("sms") == PermissionState.GRANTED) {
            call.resolve(status());
            return;
        }
        requestPermissionForAlias("sms", call, "smsPermissionCallback");
    }

    @PermissionCallback
    private void smsPermissionCallback(PluginCall call) {
        JSObject ret = status();
        // When Android refuses without asking (restricted setting for sideloaded apps, or "don't ask again"),
        // the app shows how to allow it in Settings.
        ret.put("canAskAgain", getActivity() != null && getActivity().shouldShowRequestPermissionRationale(Manifest.permission.READ_SMS));
        call.resolve(ret);
    }

    /** How many inbox messages exist and how many come from business senders (to spot phones that hide them). */
    @PluginMethod
    public void countInbox(PluginCall call) {
        if (getPermissionState("sms") != PermissionState.GRANTED) {
            call.reject("SMS permission not granted", "NO_PERMISSION");
            return;
        }
        executor.execute(() -> {
            int total = 0, business = 0;
            try (Cursor c = getContext().getContentResolver().query(Telephony.Sms.Inbox.CONTENT_URI,
                    new String[] { Telephony.Sms.ADDRESS }, null, null, null)) {
                while (c != null && c.moveToNext()) {
                    total++;
                    if ("business".equals(senderKind(c.getString(0)))) business++;
                }
                JSObject ret = new JSObject();
                ret.put("total", total);
                ret.put("business", business);
                call.resolve(ret);
            } catch (SecurityException e) {
                call.reject("SMS permission not granted", "NO_PERMISSION");
            } catch (Exception e) {
                call.reject("Couldn't read the SMS inbox: " + e.getMessage());
            }
        });
    }

    /** Messages received in [fromMs, toMs), oldest first, after the on-phone filtering. */
    @PluginMethod
    public void read(PluginCall call) {
        long from = call.getLong("fromMs", 0L);
        long to = call.getLong("toMs", Long.MAX_VALUE);
        if (getPermissionState("sms") != PermissionState.GRANTED) {
            call.reject("SMS permission not granted", "NO_PERMISSION");
            return;
        }
        executor.execute(() -> {
            String[] projection = { Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE };
            String selection = Telephony.Sms.DATE + " >= ? AND " + Telephony.Sms.DATE + " < ?";
            String[] args = { String.valueOf(from), String.valueOf(to) };
            try (Cursor c = getContext().getContentResolver().query(Telephony.Sms.Inbox.CONTENT_URI, projection, selection, args,
                    Telephony.Sms.DATE + " ASC")) {
                JSArray messages = new JSArray();
                int read = 0, personal = 0, promo = 0, otp = 0;
                long newest = 0;
                while (c != null && c.moveToNext()) {
                    String address = c.getString(0);
                    String body = c.getString(1);
                    long date = c.getLong(2);
                    read++;
                    newest = Math.max(newest, date);
                    if (address == null || body == null || body.trim().isEmpty()) continue;
                    String kind = senderKind(address);
                    if ("personal".equals(kind)) {
                        personal++;
                        continue;
                    }
                    if ("promo".equals(kind)) {
                        promo++;
                        continue;
                    }
                    if (isOtpOnly(body)) {
                        otp++;
                        continue;
                    }
                    JSObject m = new JSObject();
                    m.put("address", address.trim());
                    m.put("body", body);
                    m.put("date_ms", date);
                    messages.put(m);
                }
                JSObject ret = new JSObject();
                ret.put("messages", messages);
                ret.put("read", read);
                ret.put("skipped_personal", personal);
                ret.put("skipped_promo", promo);
                ret.put("skipped_otp", otp);
                ret.put("newest_ms", newest);
                call.resolve(ret);
            } catch (SecurityException e) {
                call.reject("SMS permission not granted", "NO_PERMISSION");
            } catch (Exception e) {
                call.reject("Couldn't read the SMS inbox: " + e.getMessage());
            }
        });
    }

    /** Opens this app's page in Android Settings (to allow the SMS permission or "restricted settings"). */
    @PluginMethod
    public void openAppSettings(PluginCall call) {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.fromParts("package", getContext().getPackageName(), null));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(intent);
        call.resolve();
    }
}
