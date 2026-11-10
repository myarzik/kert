package io.github.myarzik.kert.app

import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.myarzik.kert.core.Action
import io.github.myarzik.kert.core.BlockView
import io.github.myarzik.kert.core.BookLayout
import io.github.myarzik.kert.core.Centering
import io.github.myarzik.kert.core.LibraryEntry
import io.github.myarzik.kert.core.Palettes
import io.github.myarzik.kert.core.Reader
import io.github.myarzik.kert.core.ReaderState
import io.github.myarzik.kert.core.Settings
import io.github.myarzik.kert.core.SettingsDefaults
import io.github.myarzik.kert.core.Theme
import java.util.Locale
import kotlin.math.abs
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** §17.5 presets from core as Compose colors (§17.12). */
private data class Palette(val background: Color, val active: Color, val rest: Color, val neighbor: Color)

private fun Theme.palette(): Palette {
    val p = Palettes.of(this)
    fun color(rgb: Int) = Color(0xFF000000.toInt() or rgb)
    return Palette(color(p.background), color(p.active), color(p.rest), color(p.neighbor))
}

private fun percentText(state: ReaderState) = String.format(Locale.ROOT, "%.1f%%", state.percent)

/** The center-focus reading screen (§16.5). */
@Composable
fun ReaderScreen(
    entry: LibraryEntry,
    defaults: SettingsDefaults,
    systemDark: Boolean,
    host: ReaderHost,
    onBack: () -> Unit,
) {
    // Recap and recall stay off until the app shows their cards (§17.12 task 39).
    val fallback = Settings(
        chunkWidth = 8, theme = if (systemDark) Theme.DARK else Theme.LIGHT, recap = false, recall = false,
    )
    val controller = remember(entry.file) { ReaderController(entry.file.toFile(), defaults, fallback) }
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf<ReaderState?>(null) }
    var layout by remember { mutableStateOf<BookLayout?>(null) }
    var panel by remember { mutableStateOf(false) }

    fun dispatch(action: Action) = scope.launch { controller.dispatch(action)?.let { state = it } }

    LaunchedEffect(entry.file) {
        val opened = controller.open()
        layout = BookLayout(opened.book)
        state = opened
    }
    val view = LocalView.current
    DisposableEffect(controller) {
        view.rootView.keepScreenOn = true
        host.onKey = { code ->
            when (code) {
                KeyEvent.KEYCODE_VOLUME_DOWN -> { dispatch(Action.Next); true }
                KeyEvent.KEYCODE_VOLUME_UP -> { dispatch(Action.Previous); true }
                else -> false
            }
        }
        host.onStop = { scope.launch { controller.close() } }
        host.onStart = { scope.launch { state = controller.open() } }
        onDispose {
            view.rootView.keepScreenOn = false
            host.onKey = null
            host.onStop = null
            host.onStart = null
            controller.release()
        }
    }
    BackHandler {
        scope.launch {
            controller.close()
            onBack()
        }
    }

    val current = state
    val book = layout
    if (current == null || book == null) return
    val palette = current.settings.theme.palette()

    Box(Modifier.fillMaxSize().background(palette.background)) {
        Tape(current, book, palette, onTap = { zone ->
            when (zone) {
                Zone.TOP -> panel = !panel
                Zone.LEFT -> dispatch(Action.Previous)
                Zone.RIGHT -> dispatch(Action.Next)
            }
        }, onSwipe = { up -> dispatch(if (up) Action.NextBlock else Action.PreviousBlock) })

        Text(
            percentText(current),
            color = palette.rest,
            fontSize = 13.sp,
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp).testTag("status"),
        )
        if (panel) Panel(current, palette, ::dispatch)
    }
}

private enum class Zone { TOP, LEFT, RIGHT }

@Composable
private fun Tape(
    state: ReaderState,
    layout: BookLayout,
    palette: Palette,
    onTap: (Zone) -> Unit,
    onSwipe: (up: Boolean) -> Unit,
) {
    val (activeBlock, range) = layout.active(state)
    val activeText = layout.blocks[activeBlock].text.substring(range.first, range.last + 1)
    val list = rememberLazyListState()
    val layouts = remember { mutableStateMapOf<Int, TextLayoutResult>() }
    val density = LocalDensity.current
    val topEdge = with(density) { 56.dp.toPx() }
    val swipeThreshold = with(density) { 48.dp.toPx() }

    BoxWithConstraints(
        Modifier
            .fillMaxSize()
            .testTag("reader")
            .semantics { stateDescription = activeText }
            .pointerInput(Unit) {
                detectTapGestures { offset ->
                    onTap(
                        when {
                            offset.y < topEdge -> Zone.TOP
                            offset.x < size.width / 3f -> Zone.LEFT
                            else -> Zone.RIGHT
                        },
                    )
                }
            }
            .pointerInput(Unit) {
                var travel = 0f
                detectVerticalDragGestures(
                    onDragStart = { travel = 0f },
                    onDragEnd = { if (abs(travel) > swipeThreshold) onSwipe(travel < 0) },
                ) { _, dy -> travel += dy }
            },
    ) {
        val half = maxHeight / 2
        LazyColumn(
            state = list,
            userScrollEnabled = false, // the tape moves only with the active chunk
            contentPadding = PaddingValues(vertical = half),
            verticalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            items(layout.blocks.size) { i ->
                val block = layout.blocks[i]
                Text(
                    blockText(block, if (i == activeBlock) range else null, palette),
                    style = blockStyle(block),
                    onTextLayout = { layouts[i] = it },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp),
                )
            }
        }
    }

    // Keep the active chunk's lines on the vertical center (§7.1 / §16.5).
    LaunchedEffect(state.index, state.settings.chunkWidth, activeBlock) {
        if (list.layoutInfo.visibleItemsInfo.none { it.index == activeBlock }) list.scrollToItem(activeBlock)
        val (item, text) = snapshotFlow {
            list.layoutInfo.visibleItemsInfo.firstOrNull { it.index == activeBlock } to layouts[activeBlock]
        }.first { (item, text) -> item != null && text != null }
        val info = list.layoutInfo
        val first = text!!.getLineForOffset(range.first)
        val last = text.getLineForOffset(range.last)
        val delta = Centering.scrollDelta(
            itemTop = item!!.offset - info.viewportStartOffset,
            chunkTop = text.getLineTop(first),
            chunkBottom = text.getLineBottom(last),
            viewport = info.viewportEndOffset - info.viewportStartOffset,
        )
        list.animateScrollBy(delta)
    }
}

private fun blockStyle(block: BlockView) = TextStyle(
    fontSize = if (block.type == "code") 15.sp else 20.sp,
    lineHeight = if (block.type == "code") 22.sp else 30.sp,
    fontFamily = if (block.type == "code") FontFamily.Monospace else FontFamily.Serif,
    fontWeight = if (block.type == "heading") FontWeight.Bold else FontWeight.Normal,
)

private fun blockText(block: BlockView, active: IntRange?, palette: Palette): AnnotatedString =
    buildAnnotatedString {
        withStyle(SpanStyle(color = if (active != null) palette.rest else palette.neighbor)) {
            append(block.text)
        }
        if (active != null) {
            addStyle(SpanStyle(color = palette.active, fontWeight = FontWeight.Bold), active.first, active.last + 1)
        }
    }

/** Top panel: percent, goto, width and theme (§16.5). */
@Composable
private fun Panel(state: ReaderState, palette: Palette, dispatch: (Action) -> Unit) {
    var goto by remember(state.index) { mutableFloatStateOf(state.percent.toFloat()) }
    Column(
        Modifier.fillMaxWidth().background(palette.background).padding(horizontal = 24.dp, vertical = 16.dp),
    ) {
        Text("Go to ${String.format(Locale.ROOT, "%.0f%%", goto)}", color = palette.active)
        Slider(
            value = goto,
            onValueChange = { goto = it },
            valueRange = 0f..100f,
            onValueChangeFinished = { dispatch(Action.GotoPercent(goto.toDouble())) },
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Width ${state.settings.chunkWidth}", color = palette.active, modifier = Modifier.weight(1f))
            val width = state.settings.chunkWidth
            TextButton(onClick = { dispatch(Action.SetWidth(width - 1)) }, enabled = width > Reader.WIDTH_MIN) {
                Text("−")
            }
            TextButton(onClick = { dispatch(Action.SetWidth(width + 1)) }, enabled = width < Reader.WIDTH_MAX) {
                Text("+")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
            for (theme in Theme.entries) {
                val label = if (theme == Theme.DARK) "Dark" else "Light"
                Text(
                    label,
                    color = if (state.settings.theme == theme) palette.active else palette.rest,
                    fontWeight = if (state.settings.theme == theme) FontWeight.Bold else FontWeight.Normal,
                    modifier = Modifier
                        .selectable(
                            selected = state.settings.theme == theme,
                            onClick = { dispatch(Action.SetTheme(theme)) },
                            role = Role.RadioButton,
                        )
                        .padding(vertical = 8.dp),
                )
            }
        }
    }
}
