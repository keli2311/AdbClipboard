package ch.pete.adbclipboard

import android.annotation.SuppressLint
import android.app.Service
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.PixelFormat
import android.graphics.Point
import android.util.Log
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.Toast
import timber.log.Timber
import java.io.File
import java.io.IOException
import kotlin.math.abs
import kotlin.math.max

class FloatingViewService : Service() {
    private lateinit var windowManager: WindowManager
    private lateinit var floatingView: View
    private lateinit var prefs: SharedPreferences
    private val handler = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("InflateParams")
    override fun onCreate() {
        super.onCreate()

        floatingView = LayoutInflater.from(this).inflate(R.layout.floating_widget, null)
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)

        // Set up window parameters
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = prefs.getInt(KEY_X, 0)
        params.y = prefs.getInt(KEY_Y, 100)

        // Add view to window manager
        windowManager = getSystemService(WindowManager::class.java)
        windowManager.addView(floatingView, params)

        makeDraggable(floatingView, params)
    }

    /** 单击粘贴；长按后拖动按钮换位置，位置会被记住。 */
    @SuppressLint("ClickableViewAccessibility")
    private fun makeDraggable(
        view: View,
        params: WindowManager.LayoutParams
    ) {
        val touchSlop = ViewConfiguration.get(this).scaledTouchSlop
        val longPressTimeout = ViewConfiguration.getLongPressTimeout().toLong()
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f
        var dragging = false

        val longPressRunnable = Runnable {
            dragging = true
            view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            view.alpha = 0.85f
        }

        view.setOnTouchListener { touchedView, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    dragging = false
                    Log.d(TAG, "touch DOWN at ${event.rawX},${event.rawY}")
                    handler.removeCallbacks(longPressRunnable)
                    handler.postDelayed(longPressRunnable, longPressTimeout)
                    true
                }

                MotionEvent.ACTION_MOVE -> {
                    // 长按触发前就大幅移动：视为普通点击的滑动，取消长按（不拖动）
                    if (!dragging &&
                        (abs(event.rawX - initialTouchX) > touchSlop ||
                            abs(event.rawY - initialTouchY) > touchSlop)
                    ) {
                        handler.removeCallbacks(longPressRunnable)
                    }

                    if (dragging) {
                        val target = clampPosition(
                            view,
                            initialX + (event.rawX - initialTouchX).toInt(),
                            initialY + (event.rawY - initialTouchY).toInt()
                        )
                        params.x = target.x
                        params.y = target.y
                        windowManager.updateViewLayout(view, params)
                    }
                    true
                }

                MotionEvent.ACTION_UP -> {
                    handler.removeCallbacks(longPressRunnable)
                    Log.d(TAG, "touch UP dragging=$dragging at ${event.rawX},${event.rawY}")
                    if (dragging) {
                        dragging = false
                        view.alpha = 1f
                        savePosition(params.x, params.y)
                    } else {
                        Log.d(TAG, "tap -> requestPaste")
                        // 没有长按的轻点：执行粘贴
                        requestPaste()
                    }
                    true
                }

                MotionEvent.ACTION_CANCEL -> {
                    handler.removeCallbacks(longPressRunnable)
                    Log.d(TAG, "touch CANCEL dragging=$dragging")
                    if (dragging) {
                        dragging = false
                        view.alpha = 1f
                    }
                    true
                }

                else -> false
            }
        }
    }

    /** 把坐标限制在屏幕内，避免按钮被拖到屏幕外拿不回来。 */
    private fun clampPosition(view: View, x: Int, y: Int): Point {
        val bounds = screenBounds()
        val maxX = max(0, bounds.x - view.width)
        val maxY = max(0, bounds.y - view.height)
        return Point(x.coerceIn(0, maxX), y.coerceIn(0, maxY))
    }

    private fun screenBounds(): Point {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = windowManager.currentWindowMetrics.bounds
            Point(bounds.width(), bounds.height())
        } else {
            @Suppress("DEPRECATION")
            val metrics = resources.displayMetrics
            Point(metrics.widthPixels, metrics.heightPixels)
        }
    }

    private fun savePosition(x: Int, y: Int) {
        prefs.edit().putInt(KEY_X, x).putInt(KEY_Y, y).apply()
    }

    private fun requestPaste() {
        try {
            val dir = getExternalFilesDir(null)
            Log.d(TAG, "requestPaste dir=$dir")
            val file = File(dir, PASTE_REQUEST_FILE_NAME)
            file.writeText("")
            Log.d(TAG, "Paste request written to: ${file.absolutePath}")
            Timber.d("Paste request written to: ${file.absolutePath}")
            Toast.makeText(this, getString(R.string.paste_requested), Toast.LENGTH_SHORT).show()
        } catch (e: IOException) {
            Log.e(TAG, "Failed to write paste request: $e")
            Timber.e(e, "Failed to write paste request")
            Toast.makeText(this, getString(R.string.paste_request_failed), Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::floatingView.isInitialized) {
            windowManager.removeView(floatingView)
        }
    }

    companion object {
        private const val PREFS_NAME = "floating_widget"
        private const val KEY_X = "pos_x"
        private const val KEY_Y = "pos_y"
        private const val PASTE_REQUEST_FILE_NAME = "paste_request.txt"
        private const val TAG = "FloatingViewService"
    }
}
