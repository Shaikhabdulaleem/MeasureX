package com.aymakan.measurex.m9capture

/**
 * Write-state of every candidate JPEG, so EXPORT never races a pending image write
 * and never references a frame whose image failed to write. Thread-safe (the GL
 * thread registers writes; the writer thread resolves them) and pure Kotlin, so the
 * gate logic is unit-tested without a device.
 *
 * A failed write is *forgotten*, not left as a permanent block: the activity also
 * drops that frame from the manifest and the controller, so capture can replace it.
 */
class JpegWrites {
    enum class State { PENDING, OK, FAILED }

    private val state = linkedMapOf<String, State>()

    @Synchronized fun begin(frameId: String) { state[frameId] = State.PENDING }
    @Synchronized fun succeed(frameId: String) { state[frameId] = State.OK }
    @Synchronized fun fail(frameId: String) { state[frameId] = State.FAILED }
    @Synchronized fun forget(frameId: String) { state.remove(frameId) }
    @Synchronized fun clear() { state.clear() }

    @Synchronized fun pending(): Int = state.values.count { it == State.PENDING }
    @Synchronized fun failed(): List<String> =
        state.filterValues { it == State.FAILED }.keys.toList()

    /** Export is allowed only when nothing is pending and nothing failed. */
    @Synchronized fun exportReady(): Boolean = pending() == 0 && failed().isEmpty()
}

/**
 * The CPU image and the declared intrinsics must describe the same pixel grid, or a
 * native orientation/rotation bug has crept in. Pure predicate so the rejection rule
 * is unit-tested (the saved image itself stays unrotated/uncropped/unresized).
 */
fun imageMatchesIntrinsics(imageWidth: Int, imageHeight: Int, intrinsicsWidth: Int, intrinsicsHeight: Int): Boolean =
    imageWidth == intrinsicsWidth && imageHeight == intrinsicsHeight
