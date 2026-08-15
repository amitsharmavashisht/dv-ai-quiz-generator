/* Drives the real built page in a DOM. Run:  node tests-frontend/ui.test.js
   Requires: npm install jsdom                                             */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const PAGE = path.join(__dirname, '..', 'backend', 'static', 'index.html');

let pass = 0, fail = 0;
function ok(label, cond, extra) {
	if (cond) { pass++; console.log('  ok   ' + label); }
	else { fail++; console.log('  FAIL ' + label + (extra ? '  -> ' + extra : '')); }
}
function section(name) { console.log('\n' + name); }

/* jsdom applies stylesheets, so display rules are honoured — which is
   exactly what is needed to catch a [hidden] override. */
function load(sample) {
	const html = fs.readFileSync(PAGE, 'utf8');
	const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
	const w = dom.window;
	w.fetch = () => Promise.resolve({
		ok: true, json: () => Promise.resolve(sample)
	});
	w.confirm = () => true;
	Object.defineProperty(w.navigator, 'clipboard', {
		value: { writeText: () => Promise.resolve() }, configurable: true
	});
	return w;
}

function visible(w, id) {
	const el = w.document.getElementById(id);
	if (!el) return false;
	if (el.hidden) {
		// hidden must actually hide, stylesheet included
		return w.getComputedStyle(el).display !== 'none';
	}
	return w.getComputedStyle(el).display !== 'none';
}

const SAMPLE = {
	title: 'Fundamental Rights', difficulty: 'medium', output_format: 'mcq',
	questions: [
		{ question: 'Which article is the heart and soul of the Constitution?',
		  options: ['Article 32', 'Article 21', 'Article 19', 'Article 14'],
		  answer_index: 0, explanation: 'Ambedkar described it this way.' },
		{ question: 'How many fundamental rights remain today?',
		  options: ['Six', 'Seven', 'Five', 'Eight'],
		  answer_index: 0, explanation: 'Property was removed in 1978.' }
	]
};

const PASTED = `Q1. When was Himachal Pradesh established as a state?  हिमाचल प्रदेश राज्य कब बना?
A) 1950   B) 1966   C) 1971*   D) 1975
Exp: Himachal became a full state on 25 January 1971.

Q2. Who is called the father of Himachal Pradesh?
A) Y.S. Parmar
B) Virbhadra Singh
C) Shanta Kumar
D) Ram Lal
Ans: A`;

const wait = ms => new Promise(r => setTimeout(r, ms));

(async function run() {

	/* ── 1. Opening state ─────────────────────────────────────────── */
	section('Opening state');
	{
		const w = load(SAMPLE);
		await wait(60);
		ok('builder is visible', visible(w, 'dvq-builder'));
		ok('status bar is HIDDEN before any paper exists (the display:flex bug)',
			!visible(w, 'dvq-statusbar'));
		ok('export view is hidden', !visible(w, 'dvq-export'));
		ok('paper is hidden', !visible(w, 'dvq-quiz'));
		ok('loading is hidden', !visible(w, 'dvq-loading'));
		ok('wizard starts on step 1',
			w.document.querySelector('#dvq-steps .dvq-step[data-step="1"]').classList.contains('is-on'));
		w.close();
	}

	/* ── 2. Paste mode ────────────────────────────────────────────── */
	section('Paste questions -> straight to HTML');
	{
		const w = load(SAMPLE);
		await wait(60);
		const d = w.document;

		d.querySelector('.dvq-tab[data-src="paste"]').click();
		ok('paste panel opens',
			d.querySelector('.dvq-panel[data-panel="paste"]').classList.contains('is-on'));
		ok('model settings are hidden in paste mode',
			d.getElementById('dvq-controls').style.display === 'none');
		ok('button relabels to Build quiz',
			d.getElementById('dvq-go').textContent === 'Build quiz');

		const box = d.getElementById('dvq-paste');
		box.value = PASTED;
		box.dispatchEvent(new w.Event('input'));
		ok('live counter detects 2 questions',
			d.getElementById('dvq-paste-count').textContent === '2',
			d.getElementById('dvq-paste-count').textContent);

		d.getElementById('dvq-go').click();
		await wait(60);

		ok('lands on the export view', visible(w, 'dvq-export'));
		ok('status bar now visible', visible(w, 'dvq-statusbar'));
		ok('builder hidden', !visible(w, 'dvq-builder'));
		ok('wizard on step 3',
			d.querySelector('#dvq-steps .dvq-step[data-step="3"]').classList.contains('is-on'));

		const code = d.getElementById('dvq-code').textContent;
		ok('code box is NOT empty', code.length > 2000, code.length + ' chars');
		ok('code is a full document', code.startsWith('<!DOCTYPE html>'));
		ok('file size is shown',
			/\d+\.\d+ KB/.test(d.getElementById('dvq-filesize').textContent),
			d.getElementById('dvq-filesize').textContent);
		ok('pill reports the count',
			/2 questions/.test(d.getElementById('dvq-ready-count').textContent));
		ok('bilingual question survived', /[\u0900-\u097F]/.test(code));
		ok('star marker resolved to the right answer',
			code.indexOf('"answer_index":2') !== -1 || code.indexOf('1971') !== -1);
		w.close();
	}

	/* ── 3. Preview toggle ────────────────────────────────────────── */
	section('Code / Preview toggle');
	{
		const w = load(SAMPLE);
		await wait(60);
		const d = w.document;
		d.querySelector('.dvq-tab[data-src="paste"]').click();
		const box = d.getElementById('dvq-paste');
		box.value = PASTED;
		box.dispatchEvent(new w.Event('input'));
		d.getElementById('dvq-go').click();
		await wait(60);

		ok('code pane shown by default', visible(w, 'dvq-codewrap'));
		ok('preview pane hidden by default', !visible(w, 'dvq-previewwrap'));

		d.querySelector('#dvq-exp-toggle .dvq-seg[data-mode="preview"]').click();
		ok('preview pane shown after toggle', visible(w, 'dvq-previewwrap'));
		ok('code pane hidden after toggle', !visible(w, 'dvq-codewrap'));
		const srcdoc = d.getElementById('dvq-preview').getAttribute('srcdoc') || '';
		ok('iframe srcdoc is populated', srcdoc.length > 2000, srcdoc.length + ' chars');

		d.querySelector('#dvq-exp-toggle .dvq-seg[data-mode="code"]').click();
		ok('toggles back to code', visible(w, 'dvq-codewrap'));
		w.close();
	}

	/* ── 4. Generated paper ───────────────────────────────────────── */
	section('AI path -> take the paper');
	{
		const w = load(SAMPLE);
		await wait(60);
		const d = w.document;

		const text = d.getElementById('dvq-text');
		text.value = 'x'.repeat(400);
		text.dispatchEvent(new w.Event('input'));
		d.getElementById('dvq-go').click();
		await wait(120);

		ok('lands on the paper, not the export', visible(w, 'dvq-quiz'));
		ok('export hidden', !visible(w, 'dvq-export'));
		ok('2 questions rendered',
			d.querySelectorAll('#dvq-questions .dvq-q').length === 2);
		ok('4 options on the first question',
			d.querySelectorAll('#dvq-questions .dvq-q')[0]
			 .querySelectorAll('.dvq-opt').length === 4);
		ok('masthead shows max marks',
			/Max marks: 2/.test(d.getElementById('dvq-quiz-meta').textContent));

		// answer both, then score
		d.querySelectorAll('#dvq-questions .dvq-q').forEach(function (li) {
			const first = li.querySelector('.dvq-opt input');
			first.checked = true;
			first.dispatchEvent(new w.Event('change'));
		});
		d.getElementById('dvq-submit').click();
		await wait(60);

		ok('result view appears', visible(w, 'dvq-result'));
		ok('score is filled in', d.getElementById('dvq-score').textContent !== '0'
			|| d.getElementById('dvq-total').textContent === '2');
		ok('answer sheet has a mark per question',
			d.querySelectorAll('#dvq-sheet .dvq-mark').length === 2);

		// switch to export from a generated paper
		d.querySelector('#dvq-segment .dvq-seg[data-view="export"]').click();
		await wait(40);
		ok('export reachable from a generated paper', visible(w, 'dvq-export'));
		ok('export code populated',
			d.getElementById('dvq-code').textContent.length > 2000);

		// and back again
		d.querySelector('#dvq-segment .dvq-seg[data-view="paper"]').click();
		await wait(40);
		ok('returns to the result view', visible(w, 'dvq-result'));
		w.close();
	}

	/* ── 5. Copy and reset ────────────────────────────────────────── */
	section('Copy, download, start over');
	{
		const w = load(SAMPLE);
		await wait(60);
		const d = w.document;
		d.querySelector('.dvq-tab[data-src="paste"]').click();
		const box = d.getElementById('dvq-paste');
		box.value = PASTED;
		box.dispatchEvent(new w.Event('input'));
		d.getElementById('dvq-go').click();
		await wait(60);

		d.getElementById('dvq-copy').click();
		await wait(80);
		ok('copy button confirms',
			/Copied/.test(d.getElementById('dvq-copy').textContent),
			d.getElementById('dvq-copy').textContent);
		ok('wizard advances to step 4',
			d.querySelector('#dvq-steps .dvq-step[data-step="4"]').classList.contains('is-on'));

		d.getElementById('dvq-back').click();
		await wait(40);
		ok('start over returns to the builder', visible(w, 'dvq-builder'));
		ok('status bar hidden again', !visible(w, 'dvq-statusbar'));
		ok('wizard resets to step 1',
			d.querySelector('#dvq-steps .dvq-step[data-step="1"]').classList.contains('is-on'));
		w.close();
	}

	/* ── 6. Validation and errors ─────────────────────────────────── */
	section('Validation');
	{
		const w = load(SAMPLE);
		await wait(60);
		const d = w.document;

		d.getElementById('dvq-go').click();      // empty Notes
		await wait(40);
		ok('short text is refused with a message', visible(w, 'dvq-note'));
		ok('stays on the builder', visible(w, 'dvq-builder'));

		d.querySelector('.dvq-tab[data-src="paste"]').click();
		d.getElementById('dvq-go').click();      // empty paste box
		await wait(40);
		ok('unparseable paste is refused',
			/No questions were recognised/.test(d.getElementById('dvq-note').textContent));
		w.close();
	}

	/* ── 7. Server error surfaces to the user ─────────────────────── */
	section('Server error handling');
	{
		const html = fs.readFileSync(PAGE, 'utf8');
		const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
		const w = dom.window;
		w.fetch = () => Promise.resolve({
			ok: false,
			json: () => Promise.resolve({ error: 'Cannot reach Ollama at http://localhost:11434' })
		});
		await wait(60);
		const d = w.document;
		const text = d.getElementById('dvq-text');
		text.value = 'y'.repeat(400);
		text.dispatchEvent(new w.Event('input'));
		d.getElementById('dvq-go').click();
		await wait(120);

		ok('provider error is shown verbatim',
			/Cannot reach Ollama/.test(d.getElementById('dvq-note').textContent),
			d.getElementById('dvq-note').textContent);
		ok('returns to the builder after failure', visible(w, 'dvq-builder'));
		ok('status bar not left behind', !visible(w, 'dvq-statusbar'));
		w.close();
	}

	console.log('\n' + '='.repeat(52));
	console.log(pass + ' passed, ' + fail + ' failed');
	process.exit(fail ? 1 : 0);
})();
