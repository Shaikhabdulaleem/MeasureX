package com.example.measurex

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.InputStream
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Bluetooth Classic (SPP) bridge for MeasureX scales — Android only (PRD §9).
 *
 * Skeleton: it opens an RFCOMM/SPP socket to a paired scale and streams the raw
 * bytes it reads to Dart over an EventChannel; Dart parses them with the shared
 * WeightParser. Device selection, reconnection and per-model framing are
 * finished once a concrete scale model is chosen (PRD Q6).
 */
class ClassicScalePlugin(messenger: BinaryMessenger) :
    MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    private val methodChannel = MethodChannel(messenger, "measurex/scale_classic")
    private val eventChannel = EventChannel(messenger, "measurex/scale_classic/readings")

    private var eventSink: EventChannel.EventSink? = null
    private var socket: BluetoothSocket? = null
    private var readThread: Thread? = null
    @Volatile private var running = false

    // Standard Serial Port Profile UUID.
    private val sppUuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

    init {
        methodChannel.setMethodCallHandler(this)
        eventChannel.setStreamHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "connect" -> {
                val address = call.argument<String>("address")
                try {
                    connect(address)
                    result.success(null)
                } catch (e: Exception) {
                    result.error("CONNECT_FAILED", e.message, null)
                }
            }
            "disconnect" -> {
                disconnect()
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    private fun connect(address: String?) {
        val adapter = BluetoothAdapter.getDefaultAdapter()
            ?: throw IllegalStateException("No Bluetooth adapter")
        val device: BluetoothDevice = when {
            address != null -> adapter.getRemoteDevice(address)
            else -> adapter.bondedDevices?.firstOrNull()
                ?: throw IllegalStateException("No paired device")
        }
        val s = device.createRfcommSocketToServiceRecord(sppUuid)
        adapter.cancelDiscovery()
        s.connect()
        socket = s
        startReading(s.inputStream)
    }

    private fun startReading(input: InputStream) {
        running = true
        readThread = thread(start = true) {
            val buffer = ByteArray(1024)
            try {
                while (running) {
                    val count = input.read(buffer)
                    if (count > 0) {
                        val bytes = buffer.copyOfRange(0, count).map { it.toInt() and 0xFF }
                        eventSink?.success(bytes)
                    }
                }
            } catch (e: Exception) {
                eventSink?.error("READ_FAILED", e.message, null)
            }
        }
    }

    private fun disconnect() {
        running = false
        readThread?.interrupt()
        readThread = null
        try {
            socket?.close()
        } catch (_: Exception) {
        }
        socket = null
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        eventSink = events
    }

    override fun onCancel(arguments: Any?) {
        eventSink = null
    }
}
