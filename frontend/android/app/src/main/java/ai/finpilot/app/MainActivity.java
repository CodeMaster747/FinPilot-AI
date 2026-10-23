package ai.finpilot.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SmsInboxPlugin.class); // local plugin: must be registered before the bridge starts
        super.onCreate(savedInstanceState);
    }
}
