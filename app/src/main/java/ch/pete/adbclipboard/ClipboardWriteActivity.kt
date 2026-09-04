package ch.pete.adbclipboard

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.media.RingtoneManager
import android.os.Bundle
import timber.log.Timber

/**
 * Transparent bridge activity that writes the clipboard while the app is in the
 * foreground. Android/MIUI deny clipboard writes from background broadcast
 * receivers, so WriteReceiver routes writes through this activity.
 */
class ClipboardWriteActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val text = intent?.getStringExtra(EXTRA_TEXT).orEmpty()
        if (text.isNotEmpty()) {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText(text, text))

            val notification = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            RingtoneManager.getRingtone(this, notification)?.play()
            Timber.d("Clipboard updated via foreground activity")
        }

        finish()
    }

    companion object {
        const val EXTRA_TEXT = "text"
    }
}
