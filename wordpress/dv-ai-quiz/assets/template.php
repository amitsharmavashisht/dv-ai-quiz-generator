<?php if ( ! defined( 'ABSPATH' ) ) { exit; } ?>

<div class="dvq" id="dvq-root">

	<header class="dvq-head">
		<p class="dvq-eyebrow">DV Digital · Practice paper</p>
		<h2 class="dvq-title"><?php echo esc_html( $atts['heading'] ); ?></h2>
		<p class="dvq-intro"><?php echo esc_html( $atts['intro'] ); ?></p>
	</header>

	<!-- ── Four steps ───────────────────────────────────────────── -->
	<nav class="dvq-steps" id="dvq-steps" aria-label="Progress">
		<button class="dvq-step is-on" data-step="1"><b>1</b>Add questions</button>
		<button class="dvq-step" data-step="2"><b>2</b>Build<span> quiz</span></button>
		<button class="dvq-step" data-step="3"><b>3</b>Copy<span> HTML</span></button>
		<button class="dvq-step" data-step="4"><b>4</b>Paste<span> in WordPress</span></button>
	</nav>

	<!-- ── Ready badge ──────────────────────────────────────────── -->
	<div class="dvq-ready" id="dvq-ready" hidden>
		<span class="dvq-ready-dot"><i></i>Quiz ready</span>
		<span class="dvq-ready-count" id="dvq-ready-count">0 questions</span>
	</div>

	<!-- ── Switcher ─────────────────────────────────────────────── -->
	<div class="dvq-statusbar" id="dvq-statusbar" hidden>
		<button class="dvq-back" id="dvq-back">
			<span aria-hidden="true">←</span> Start over
		</button>
		<div class="dvq-segment" id="dvq-segment">
			<button class="dvq-seg is-on" data-view="paper">Take it</button>
			<button class="dvq-seg" data-view="export">Get HTML</button>
		</div>
	</div>

	<!-- ── Builder ──────────────────────────────────────────────── -->
	<section class="dvq-card" id="dvq-builder">

		<div class="dvq-tabs" role="tablist" aria-label="Choose your source">
			<button class="dvq-tab is-on" role="tab" aria-selected="true" data-src="text">Notes</button>
			<button class="dvq-tab" role="tab" aria-selected="false" data-src="file">File</button>
			<button class="dvq-tab" role="tab" aria-selected="false" data-src="url">Web page</button>
			<button class="dvq-tab" role="tab" aria-selected="false" data-src="youtube">YouTube</button>
			<button class="dvq-tab" role="tab" aria-selected="false" data-src="paste">Paste questions</button>
		</div>

		<div class="dvq-panels">
			<div class="dvq-panel is-on" data-panel="text">
				<textarea id="dvq-text" rows="8"
				          placeholder="Paste a chapter, your notes, or a previous year paper…"></textarea>
				<p class="dvq-count"><span id="dvq-chars">0</span> characters · 200 minimum</p>
			</div>

			<div class="dvq-panel" data-panel="file">
				<label class="dvq-drop" id="dvq-drop">
					<input type="file" id="dvq-file" accept=".pdf,.docx,.pptx,.txt,.md" hidden>
					<span class="dvq-drop-icon" aria-hidden="true">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
							<path d="M12 16V4m0 0L8 8m4-4 4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
							      stroke-linecap="round" stroke-linejoin="round"/>
						</svg>
					</span>
					<span class="dvq-drop-main">Drop a file here, or click to browse</span>
					<span class="dvq-drop-sub">PDF · DOCX · PPTX · TXT — max 20 MB</span>
				</label>
				<p class="dvq-filename" id="dvq-filename" hidden></p>
			</div>

			<div class="dvq-panel" data-panel="url">
				<input type="url" id="dvq-url" placeholder="https://example.com/article">
				<p class="dvq-count">The readable text of the page is used</p>
			</div>

			<div class="dvq-panel" data-panel="youtube">
				<input type="url" id="dvq-yt" placeholder="https://youtube.com/watch?v=…">
				<p class="dvq-count">The video needs captions</p>
			</div>

			<div class="dvq-panel" data-panel="paste">
				<div class="dvq-format-hint">
					<p class="dvq-hint-label">Supported format</p>
<pre>Q1. When was Himachal Pradesh established as a state?  हिमाचल प्रदेश राज्य कब बना?
A) 1950   B) 1966   C) 1971*   D) 1975
Exp: Himachal became a full state on 25 January 1971.</pre>
					<p class="dvq-hint-note">Mark the right option with <b>*</b>, or add a line
					<b>Ans: C</b>. English and Hindi can sit on the same line. Options may run
					across one line or four. No AI is used here — parsing is instant and free.</p>
				</div>
				<textarea id="dvq-paste" rows="10"
				          placeholder="Paste your questions with options here…"></textarea>
				<p class="dvq-count"><b id="dvq-paste-count">0</b> questions detected</p>
			</div>
		</div>

		<div class="dvq-controls" id="dvq-controls">
			<label class="dvq-field">
				<span>Questions</span>
				<select id="dvq-count-sel">
					<option>5</option><option selected>10</option>
					<option>15</option><option>20</option><option>25</option>
				</select>
			</label>
			<label class="dvq-field">
				<span>Format</span>
				<select id="dvq-format">
					<option value="mcq" selected>Multiple choice</option>
					<option value="short">Question &amp; answer</option>
				</select>
			</label>
			<label class="dvq-field">
				<span>Level</span>
				<select id="dvq-difficulty">
					<option value="easy">Easy</option>
					<option value="medium" selected>Medium</option>
					<option value="hard">Hard</option>
				</select>
			</label>
			<label class="dvq-field">
				<span>Language</span>
				<select id="dvq-language">
					<option value="auto" selected>Match source</option>
					<option value="English">English</option>
					<option value="Hindi">Hindi</option>
				</select>
			</label>
			<label class="dvq-field dvq-field-wide">
				<span>Focus topic <em>optional</em></span>
				<input type="text" id="dvq-topic" placeholder="e.g. Normalisation, Kirchhoff's laws">
			</label>
			<label class="dvq-switch">
				<input type="checkbox" id="dvq-instant">
				<span>Show each answer as I go</span>
			</label>
		</div>

		<button class="dvq-go" id="dvq-go">Generate paper</button>
		<p class="dvq-note" id="dvq-note" role="alert" hidden></p>
	</section>

	<!-- ── Loading ──────────────────────────────────────────────── -->
	<section class="dvq-card dvq-loading" id="dvq-loading" hidden>
		<div class="dvq-bubbles" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
		<p class="dvq-loading-main" id="dvq-loading-text">Reading your material…</p>
		<div class="dvq-track"><i id="dvq-track-fill"></i></div>
	</section>

	<!-- ── Paper ────────────────────────────────────────────────── -->
	<section id="dvq-quiz" hidden>
		<div class="dvq-quiz-head">
			<h3 id="dvq-quiz-title"></h3>
			<p class="dvq-meta" id="dvq-quiz-meta"></p>
		</div>
		<ol class="dvq-questions" id="dvq-questions"></ol>
		<div class="dvq-actions">
			<button class="dvq-go" id="dvq-submit">Check answers</button>
			<button class="dvq-ghost" id="dvq-csv">Download CSV</button>
		</div>
	</section>

	<!-- ── Result ───────────────────────────────────────────────── -->
	<section class="dvq-card dvq-result" id="dvq-result" hidden>
		<p class="dvq-eyebrow dvq-centred">Answer key</p>
		<p class="dvq-score"><span id="dvq-score">0</span><span class="dvq-of">/<span id="dvq-total">0</span></span></p>
		<p class="dvq-verdict" id="dvq-verdict"></p>
		<div class="dvq-sheet" id="dvq-sheet" aria-label="Answer sheet"></div>
		<div class="dvq-actions">
			<button class="dvq-ghost" id="dvq-review">Review answers</button>
			<button class="dvq-ghost" id="dvq-print">Print</button>
			<button class="dvq-go" id="dvq-again">Try again</button>
		</div>
	</section>

	<!-- ── Export ───────────────────────────────────────────────── -->
	<section id="dvq-export" hidden>
		<div class="dvq-exp-bar">
			<div class="dvq-segment dvq-segment-sm" id="dvq-exp-toggle">
				<button class="dvq-seg is-on" data-mode="code">Code</button>
				<button class="dvq-seg" data-mode="preview">Preview</button>
			</div>
			<p class="dvq-filemeta"><b>quiz.html</b><span id="dvq-filesize">—</span></p>
		</div>

		<div class="dvq-codewrap" id="dvq-codewrap">
			<div class="dvq-codebar">
				<span class="dvq-dots" aria-hidden="true"><i></i><i></i><i></i></span>
				<span class="dvq-codename">quiz.html</span>
			</div>
			<pre class="dvq-code" id="dvq-code"></pre>
		</div>

		<div class="dvq-previewwrap" id="dvq-previewwrap" hidden>
			<iframe id="dvq-preview" title="Quiz preview" sandbox="allow-scripts"></iframe>
		</div>

		<div class="dvq-actions">
			<button class="dvq-go dvq-go-copy" id="dvq-copy">Copy HTML code</button>
			<button class="dvq-ghost" id="dvq-download">Download .html</button>
		</div>

		<div class="dvq-howto">
			<p class="dvq-hint-label">How to use it</p>
			<ol>
				<li>Copy the HTML above.</li>
				<li>In WordPress, add a <b>Custom HTML</b> block — in Elementor use the
					<b>HTML</b> widget — and paste it in.</li>
				<li>Publish. The quiz runs entirely in the reader's browser, so this page
					never calls the API again.</li>
			</ol>
			<p class="dvq-hint-note">Or save it as <b>quiz.html</b> and open it directly.
			Nothing loads from outside, so it works offline too.</p>
		</div>
	</section>

</div>
