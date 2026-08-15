/* DV Digital — AI Quiz Generator (vanilla, no dependencies) */
(function () {
	'use strict';

	var root = document.getElementById('dvq-root');
	if (!root || typeof DVQ === 'undefined') { return; }

	var $ = function (id) { return document.getElementById(id); };
	var LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];

	var state = {
		source: 'text',
		file: null,
		quiz: null,
		answers: {},
		html: '',
		scored: false
	};

	/* ── View routing ────────────────────────────────────────────── */

	var VIEWS = {
		builder: ['dvq-steps', 'dvq-builder'],
		loading: ['dvq-steps', 'dvq-loading'],
		paper:   ['dvq-steps', 'dvq-ready', 'dvq-statusbar', 'dvq-quiz'],
		result:  ['dvq-steps', 'dvq-ready', 'dvq-statusbar', 'dvq-quiz', 'dvq-result'],
		export:  ['dvq-steps', 'dvq-ready', 'dvq-statusbar', 'dvq-export']
	};

	var ALL = ['dvq-steps', 'dvq-ready', 'dvq-builder', 'dvq-loading',
	           'dvq-statusbar', 'dvq-quiz', 'dvq-result', 'dvq-export'];

	// Which of the four steps each view sits on.
	var STEP_OF = { builder: 1, loading: 2, paper: 2, result: 2, export: 3 };

	function paintSteps(current) {
		root.querySelectorAll('.dvq-step').forEach(function (el) {
			var n = +el.dataset.step;
			el.classList.toggle('is-on', n === current);
			el.classList.toggle('is-done', n < current);
		});
	}

	function showView(name) {
		var wanted = VIEWS[name] || [];
		ALL.forEach(function (id) {
			var el = $(id);
			if (el) { el.hidden = wanted.indexOf(id) === -1; }
		});

		root.querySelectorAll('#dvq-segment .dvq-seg').forEach(function (b) {
			var target = name === 'export' ? 'export' : 'paper';
			b.classList.toggle('is-on', b.dataset.view === target);
		});

		paintSteps(STEP_OF[name] || 1);
		if (root.scrollIntoView) {
			root.scrollIntoView({ behavior: 'smooth', block: 'start' });
		}
	}

	// Step 4 is a note, not a destination. Steps 1-3 jump where they can.
	root.querySelectorAll('.dvq-step').forEach(function (el) {
		el.addEventListener('click', function () {
			var n = +el.dataset.step;
			if (n === 1) { return goBuilder(); }
			if (!state.quiz) { return; }
			if (n === 2) { showView(state.scored ? 'result' : 'paper'); }
			if (n === 3 && openExport()) { return; }
		});
	});

	/* ── Source tabs ─────────────────────────────────────────────── */

	root.querySelectorAll('.dvq-tab').forEach(function (tab) {
		tab.addEventListener('click', function () {
			state.source = tab.dataset.src;

			root.querySelectorAll('.dvq-tab').forEach(function (t) {
				var on = t === tab;
				t.classList.toggle('is-on', on);
				t.setAttribute('aria-selected', on ? 'true' : 'false');
			});
			root.querySelectorAll('.dvq-panel').forEach(function (p) {
				p.classList.toggle('is-on', p.dataset.panel === state.source);
			});

			// Model settings mean nothing when the questions are supplied directly.
			var pasting = state.source === 'paste';
			$('dvq-controls').style.display = pasting ? 'none' : '';
			$('dvq-go').textContent = pasting ? 'Build quiz' : 'Generate paper';
			hideNote();
		});
	});

	$('dvq-text').addEventListener('input', function () {
		$('dvq-chars').textContent = this.value.length.toLocaleString();
	});

	/* ── File picking and drag/drop ──────────────────────────────── */

	var drop = $('dvq-drop');

	$('dvq-file').addEventListener('change', function () { acceptFile(this.files[0]); });

	['dragenter', 'dragover'].forEach(function (ev) {
		drop.addEventListener(ev, function (e) {
			e.preventDefault();
			drop.classList.add('is-over');
		});
	});

	['dragleave', 'drop'].forEach(function (ev) {
		drop.addEventListener(ev, function (e) {
			e.preventDefault();
			drop.classList.remove('is-over');
		});
	});

	drop.addEventListener('drop', function (e) {
		if (e.dataTransfer.files.length) { acceptFile(e.dataTransfer.files[0]); }
	});

	function acceptFile(file) {
		if (!file) { return; }
		if (file.size > DVQ.maxMb * 1024 * 1024) {
			showNote('That file is over ' + DVQ.maxMb + ' MB. Upload a smaller one.');
			return;
		}
		state.file = file;
		var label = $('dvq-filename');
		label.textContent = file.name + '  \u00b7  ' + (file.size / 1048576).toFixed(1) + ' MB';
		label.hidden = false;
		hideNote();
	}

	/* ── Messages ────────────────────────────────────────────────── */

	function showNote(message) {
		var note = $('dvq-note');
		note.textContent = message;
		note.hidden = false;
	}

	function hideNote() { $('dvq-note').hidden = true; }

	/* ── Pasted questions: parsed here, no API call ──────────────── */

	var OPT_RE  = /^\s*[\(\[]?([A-Da-d])[\)\].:\-]\s*(.+?)\s*$/;
	var ANS_RE  = /^\s*(?:ans|answer|correct|sahi|उत्तर)\s*[:\-.]?\s*[\(\[]?([A-Da-d])[\)\]]?\s*$/i;
	var EXP_RE  = /^\s*(?:exp|explanation|reason|व्याख्या)\s*[:\-.]\s*(.+)$/i;
	var QNUM_RE = /^\s*(?:Q|Que|Ques|Question|प्रश्न)?\s*\d+\s*[\).:\-]\s*(.+)$/i;
	var MARK_RE = /^(.*?)\s*(?:\*|\u2713|\u2714|\(correct\)|\[correct\])\s*$/i;

	function letterIndex(ch) { return ch.toUpperCase().charCodeAt(0) - 65; }

	function stripMarker(text) {
		var m = MARK_RE.exec(text);
		return m ? [m[1].trim(), true] : [text.trim(), false];
	}

	/* Options may be one per line, or several on a single line:
	   "A) 1950   B) 1966   C) 1971*   D) 1975" */
	function splitInlineOptions(line) {
		var parts = line.split(/\s{2,}(?=[\(\[]?[A-Da-d][\)\].:\-]\s)/);
		return parts.length > 1 ? parts : null;
	}

	function parsePasted(raw) {
		var lines = (raw || '').replace(/\r/g, '').split('\n');
		var questions = [];
		var cur = null;

		function flush() {
			if (cur && cur.question && cur.options.length >= 2) {
				if (cur.answer_index === null ||
					cur.answer_index >= cur.options.length) { cur.answer_index = 0; }
				questions.push(cur);
			}
			cur = null;
		}

		function addOption(text) {
			var m = OPT_RE.exec(text);
			if (!m) { return false; }
			var pair = stripMarker(m[2]);
			cur.options.push(pair[0]);
			if (pair[1]) { cur.answer_index = cur.options.length - 1; }
			return true;
		}

		lines.forEach(function (line) {
			var t = line.trim();
			if (!t) { return; }

			if (cur) {
				var ans = ANS_RE.exec(t);
				if (ans) { cur.answer_index = letterIndex(ans[1]); return; }

				var exp = EXP_RE.exec(t);
				if (exp) { cur.explanation = exp[1]; return; }

				if (cur.question) {
					var inline = splitInlineOptions(t);
					if (inline && inline.every(function (p) { return OPT_RE.test(p); })) {
						inline.forEach(addOption);
						return;
					}
					if (addOption(t)) { return; }
				}
			}

			flush();
			var qn = QNUM_RE.exec(t);
			cur = { question: qn ? qn[1] : t, options: [],
			        answer_index: null, explanation: '' };
		});

		flush();
		return questions;
	}

	$('dvq-paste').addEventListener('input', function () {
		$('dvq-paste-count').textContent = parsePasted(this.value).length;
	});

	function buildFromPaste() {
		var questions = parsePasted($('dvq-paste').value);
		if (!questions.length) {
			showNote('No questions were recognised. Check the format above — each ' +
			         'question needs at least two options.');
			return null;
		}
		return {
			title: 'Practice Paper',
			difficulty: 'mixed',
			output_format: 'mcq',
			questions: questions
		};
	}

	/* ── Generate ────────────────────────────────────────────────── */

	var STAGES = [
		'Reading your material\u2026',
		'Picking out what matters\u2026',
		'Writing the questions\u2026',
		'Checking the answer key\u2026',
		'Almost there \u2014 a local model takes a little longer\u2026'
	];

	function buildForm() {
		var form = new FormData();
		form.append('source_type', state.source);
		form.append('num_questions', $('dvq-count-sel').value);
		form.append('difficulty', $('dvq-difficulty').value);
		form.append('language', $('dvq-language').value);
		form.append('output_format', $('dvq-format').value);
		form.append('focus_topic', $('dvq-topic').value.trim());

		if (state.source === 'text') {
			var text = $('dvq-text').value.trim();
			if (text.length < 200) {
				showNote('Add a bit more text \u2014 about 200 characters is the minimum.');
				return null;
			}
			form.append('text', text);
		} else if (state.source === 'file') {
			if (!state.file) { showNote('Choose a file first.'); return null; }
			form.append('file', state.file);
		} else {
			var url = (state.source === 'url' ? $('dvq-url') : $('dvq-yt')).value.trim();
			if (!url) { showNote('Paste a link first.'); return null; }
			form.append('url', url);
		}
		return form;
	}

	$('dvq-go').addEventListener('click', function () {
		hideNote();

		if (state.source === 'paste') {
			var local = buildFromPaste();
			if (local) { renderQuiz(local, 'export'); }
			return;
		}

		var form = buildForm();
		if (!form) { return; }

		showView('loading');
		var step = 0;
		$('dvq-loading-text').textContent = STAGES[0];
		$('dvq-track-fill').style.width = '8%';

		var ticker = setInterval(function () {
			step = Math.min(step + 1, STAGES.length - 1);
			$('dvq-loading-text').textContent = STAGES[step];
			$('dvq-track-fill').style.width = (12 + step * 19) + '%';
		}, 3400);

		var headers = {};
		if (DVQ.nonce) { headers['X-WP-Nonce'] = DVQ.nonce; }

		fetch(DVQ.endpoint, { method: 'POST', headers: headers, body: form })
			.then(function (res) {
				return res.json().then(function (data) {
					if (!res.ok) { throw new Error(data.error || 'Something went wrong.'); }
					return data;
				});
			})
			.then(function (quiz) {
				clearInterval(ticker);
				$('dvq-track-fill').style.width = '100%';
				renderQuiz(quiz);
			})
			.catch(function (err) {
				clearInterval(ticker);
				showView('builder');
				showNote(err.message || 'The paper could not be created. Try again.');
			});
	});

	/* ── Render the paper ────────────────────────────────────────── */

	function renderQuiz(quiz, landOn) {
		state.quiz = quiz;
		state.answers = {};
		state.html = '';
		state.scored = false;

		var n = quiz.questions.length;
		var isShort = quiz.output_format === 'short';

		$('dvq-quiz-title').textContent = quiz.title;
		$('dvq-quiz-meta').textContent = isShort
			? 'Q. ' + n + '   \u00b7   Level: ' + quiz.difficulty
			: 'Q. ' + n + '   \u00b7   Level: ' + quiz.difficulty +
			  '   \u00b7   Max marks: ' + n;

		$('dvq-ready-count').textContent = n + (n === 1 ? ' question' : ' questions');

		var list = $('dvq-questions');
		list.textContent = '';

		quiz.questions.forEach(function (q, i) {
			var li = document.createElement('li');
			li.className = 'dvq-q';
			li.dataset.n = i + 1;

			var stem = document.createElement('p');
			stem.className = 'dvq-q-text';
			stem.textContent = q.question;
			li.appendChild(stem);

			if (isShort) {
				var reveal = document.createElement('button');
				reveal.className = 'dvq-reveal';
				reveal.type = 'button';
				reveal.textContent = 'Show answer';
				reveal.addEventListener('click', function () {
					var ans = document.createElement('p');
					ans.className = 'dvq-answer';
					ans.textContent = q.answer;
					li.appendChild(ans);
					reveal.remove();
				});
				li.appendChild(reveal);
				list.appendChild(li);
				return;
			}

			q.options.forEach(function (opt, j) {
				var label = document.createElement('label');
				label.className = 'dvq-opt';

				var input = document.createElement('input');
				input.type = 'radio';
				input.name = 'dvq-q' + i;
				input.value = j;
				input.addEventListener('change', function () {
					state.answers[i] = j;
					if ($('dvq-instant').checked) { markOne(li, i); }
				});

				var bubble = document.createElement('span');
				bubble.className = 'dvq-bubble';
				bubble.textContent = LETTERS[j];

				var text = document.createElement('span');
				text.className = 'dvq-opt-text';
				text.textContent = opt;

				label.append(input, bubble, text);
				li.appendChild(label);
			});

			list.appendChild(li);
		});

		$('dvq-submit').hidden = isShort;

		// openExport() renders and switches the view itself.
		if (landOn === 'export' && openExport()) { return; }
		showView('paper');
	}

	function markOne(li, index) {
		if (li.classList.contains('is-marked')) { return; }
		var q = state.quiz.questions[index];
		var chosen = state.answers[index];

		li.classList.add('is-marked');
		li.querySelectorAll('.dvq-opt').forEach(function (opt, j) {
			opt.querySelector('input').disabled = true;
			if (j === q.answer_index) { opt.classList.add('is-right'); }
			else if (j === chosen) { opt.classList.add('is-wrong'); }
		});

		if (q.explanation) {
			var why = document.createElement('p');
			why.className = 'dvq-why';
			why.textContent = q.explanation;
			li.appendChild(why);
		}
	}

	/* ── Scoring ─────────────────────────────────────────────────── */

	$('dvq-submit').addEventListener('click', function () {
		var total = state.quiz.questions.length;
		var answered = Object.keys(state.answers).length;

		if (answered < total && !confirm(
			'You have ' + (total - answered) + ' question(s) left. Check answers anyway?'
		)) { return; }

		var score = 0;
		root.querySelectorAll('.dvq-q').forEach(function (li, i) {
			markOne(li, i);
			if (state.answers[i] === state.quiz.questions[i].answer_index) { score++; }
		});

		this.hidden = true;
		state.scored = true;

		$('dvq-score').textContent = score;
		$('dvq-total').textContent = total;

		var pct = Math.round((score / total) * 100);
		$('dvq-verdict').textContent =
			pct >= 80 ? pct + '% \u2014 strong. Move on to the next topic.' :
			pct >= 50 ? pct + '% \u2014 solid base. Revise the ones you missed.' :
			            pct + '% \u2014 go back over this chapter, then try again.';

		var sheet = $('dvq-sheet');
		sheet.textContent = '';
		state.quiz.questions.forEach(function (q, i) {
			var mark = document.createElement('span');
			var ok = state.answers[i] === q.answer_index;
			mark.className = 'dvq-mark ' + (ok ? 'is-right' : 'is-wrong');
			mark.textContent = i + 1;
			mark.title = 'Question ' + (i + 1) + ' \u2014 ' + (ok ? 'correct' : 'incorrect');
			sheet.appendChild(mark);
		});

		showView('result');
		if ($('dvq-result').scrollIntoView) { $('dvq-result').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
	});

	/* ── Helpers ─────────────────────────────────────────────────── */

	function slug(title) {
		return (title || 'quiz').replace(/[^\w\s-]/g, '').trim()
			.replace(/\s+/g, '-').toLowerCase() || 'quiz';
	}

	function saveBlob(content, type, filename) {
		var url = URL.createObjectURL(new Blob([content], { type: type }));
		var a = document.createElement('a');
		a.href = url;
		a.download = filename;
		document.body.appendChild(a);
		a.click();
		a.remove();
		URL.revokeObjectURL(url);
	}

	/* ── CSV ─────────────────────────────────────────────────────── */

	function csvCell(value) {
		return '"' + String(value === undefined ? '' : value).replace(/"/g, '""') + '"';
	}

	$('dvq-csv').addEventListener('click', function () {
		if (!state.quiz) { return; }
		var short = state.quiz.output_format === 'short';
		var rows = [short
			? ['Question', 'Answer']
			: ['Question', 'Option A', 'Option B', 'Option C', 'Option D',
			   'Answer', 'Explanation']];

		state.quiz.questions.forEach(function (q) {
			rows.push(short
				? [q.question, q.answer]
				: [q.question].concat(q.options,
					[LETTERS[q.answer_index] + '. ' + q.options[q.answer_index],
					 q.explanation]));
		});

		var csv = '\ufeff' + rows.map(function (r) {
			return r.map(csvCell).join(',');
		}).join('\r\n');

		saveBlob(csv, 'text/csv;charset=utf-8;', slug(state.quiz.title) + '.csv');
	});

	/* ── Standalone HTML export ──────────────────────────────────── */

	function buildStandalone(quiz) {
		var payload = JSON.stringify(quiz)
			.replace(/</g, '\\u003c')
			.replace(/>/g, '\\u003e')
			.replace(/&/g, '\\u0026');

		return [
'<!DOCTYPE html>',
'<html lang="en">',
'<head>',
'<meta charset="utf-8">',
'<meta name="viewport" content="width=device-width, initial-scale=1">',
'<title>' + quiz.title.replace(/[<>&"]/g, '') + '</title>',
'<style>',
'.dvqx{--ink:#14161b;--mut:#7c7e88;--line:#e6e3d9;--stock:#faf8f3;--mark:#ffc800;',
'--ok:#14764a;--okbg:#edf6f1;--no:#bf342a;--nobg:#fdf1f0;max-width:720px;',
'margin:32px auto;padding:0 16px;color:var(--ink);line-height:1.6;font-size:16px;',
'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}',
'.dvqx *{box-sizing:border-box}',
'.dvqx-card{background:#fff;border:1px solid var(--line);border-radius:4px;padding:24px;',
'box-shadow:0 10px 28px -22px rgba(20,22,27,.5)}',
'.dvqx-head{text-align:center;padding:14px 0 12px;margin-bottom:18px;',
'border-top:3px double var(--ink);border-bottom:3px double var(--ink)}',
'.dvqx-head h3{margin:0 0 7px;font-size:20px;font-weight:800;text-transform:uppercase;',
'letter-spacing:-.01em;line-height:1.25}',
'.dvqx-meta{margin:0;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;',
'letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}',
'.dvqx-bar{height:3px;background:var(--line);margin-bottom:18px;overflow:hidden}',
'.dvqx-bar i{display:block;height:100%;background:var(--mark);transition:width .3s}',
'.dvqx-q{font-size:17px;font-weight:600;line-height:1.5;margin:0 0 18px}',
'.dvqx-opt{display:flex;align-items:flex-start;gap:13px;padding:11px 13px;',
'margin-bottom:6px;border:1px solid var(--line);border-radius:3px;cursor:pointer;',
'transition:border-color .15s,background .15s}',
'.dvqx-opt:hover{border-color:var(--ink);background:var(--stock)}',
'.dvqx-opt input{position:absolute;opacity:0;pointer-events:none}',
'.dvqx-b{flex:0 0 auto;display:grid;place-items:center;width:25px;height:25px;',
'margin-top:1px;border:1.5px solid #b9b6ab;border-radius:50%;font-weight:700;',
'font-family:ui-monospace,monospace;font-size:11px;color:var(--mut)}',
'.dvqx-opt input:checked~.dvqx-b{background:var(--ink);border-color:var(--ink);color:var(--mark)}',
'.dvqx-opt.ok{background:var(--okbg);border-color:var(--ok)}',
'.dvqx-opt.ok .dvqx-b{background:var(--ok);border-color:var(--ok);color:#fff}',
'.dvqx-opt.no{background:var(--nobg);border-color:var(--no)}',
'.dvqx-opt.no .dvqx-b{background:var(--no);border-color:var(--no);color:#fff}',
'.dvqx-why{margin-top:14px;padding:12px 14px;border-left:3px solid var(--mark);',
'background:var(--stock);font-size:14.5px;color:#40434c}',
'.dvqx-nav{display:flex;gap:10px;margin-top:22px;padding-top:18px;',
'border-top:1px solid var(--line)}',
'.dvqx-btn{flex:1;padding:13px 18px;border:1px solid var(--ink);border-radius:3px;',
'background:#fff;font:inherit;font-size:14.5px;font-weight:600;color:var(--ink);cursor:pointer}',
'.dvqx-btn:hover:not(:disabled){background:var(--ink);color:#fff}',
'.dvqx-btn:disabled{opacity:.35;cursor:not-allowed}',
'.dvqx-btn.solid{background:var(--ink);color:#fff}',
'.dvqx-btn.solid:hover{background:#000}',
'.dvqx-score{font-family:ui-monospace,monospace;font-size:56px;font-weight:700;',
'line-height:1;letter-spacing:-.04em;margin:8px 0 10px}',
'.dvqx-score span{font-size:.42em;font-weight:400;color:var(--mut)}',
'.dvqx-sheet{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;',
'padding:18px 12px;margin:18px 0;border-top:1px dashed #c9c5b8;',
'border-bottom:1px dashed #c9c5b8;background:var(--stock)}',
'.dvqx-m{display:grid;place-items:center;width:25px;height:25px;border-radius:50%;',
'border:1.5px solid #b9b6ab;background:#fff;font-family:ui-monospace,monospace;',
'font-size:10.5px;font-weight:700;color:var(--mut)}',
'.dvqx-m.ok{background:var(--ok);border-color:var(--ok);color:#fff}',
'.dvqx-m.no{background:var(--no);border-color:var(--no);color:#fff}',
'@media(max-width:560px){.dvqx-card{padding:16px}.dvqx-nav{flex-wrap:wrap}',
'.dvqx-btn{flex:1 1 100%}}',
'</style>',
'</head>',
'<body>',
'<div class="dvqx" id="dvqx"></div>',
'<script>',
'(function(){',
'var Q=' + payload + ';',
'var L=["A","B","C","D","E","F"],root=document.getElementById("dvqx"),i=0,picked={},done=false;',
'function esc(t){var d=document.createElement("div");d.textContent=t;return d.innerHTML;}',
'function draw(){',
' if(done){return result();}',
' var q=Q.questions[i],pct=((i+1)/Q.questions.length)*100;',
' var h=\'<div class="dvqx-head"><h3>\'+esc(Q.title)+\'</h3><p class="dvqx-meta">Question \'+(i+1)+\' of \'+Q.questions.length+\'</p></div>\';',
' h+=\'<div class="dvqx-bar"><i style="width:\'+pct+\'%"></i></div>\';',
' h+=\'<div class="dvqx-card"><p class="dvqx-q">\'+esc(q.question)+\'</p>\';',
' q.options.forEach(function(o,j){',
'  var cls="dvqx-opt",chk=picked[i]===j?" checked":"";',
'  if(picked[i]!==undefined&&picked[i]!==null){',
'   if(j===q.answer_index){cls+=" ok";}else if(j===picked[i]){cls+=" no";}}',
'  h+=\'<label class="\'+cls+\'"><input type="radio" name="dvqx-q"\'+chk+\' data-j="\'+j+\'">\'+',
'     \'<span class="dvqx-b">\'+L[j]+\'</span><span>\'+esc(o)+\'</span></label>\';});',
' if(picked[i]!==undefined&&picked[i]!==null&&q.explanation){h+=\'<p class="dvqx-why">\'+esc(q.explanation)+\'</p>\';}',
' h+=\'<div class="dvqx-nav">\';',
' h+=\'<button class="dvqx-btn" id="dvqx-prev"\'+(i===0?" disabled":"")+\'>Previous</button>\';',
' h+=\'<button class="dvqx-btn solid" id="dvqx-next">\'+(i===Q.questions.length-1?"Finish":"Next")+\'</button>\';',
' h+=\'</div></div>\';',
' root.innerHTML=h;',
' root.querySelectorAll(".dvqx-opt input").forEach(function(inp){',
'  inp.addEventListener("change",function(){picked[i]=+this.dataset.j;draw();});});',
' var p=document.getElementById("dvqx-prev");if(p){p.onclick=function(){if(i>0){i--;draw();}};}',
' document.getElementById("dvqx-next").onclick=function(){',
'  if(i<Q.questions.length-1){i++;draw();}else{done=true;draw();}};',
'}',
'function result(){',
' var s=0;Q.questions.forEach(function(q,k){if(picked[k]===q.answer_index){s++;}});',
' var pct=Math.round(s/Q.questions.length*100);',
' var v=pct>=80?"Strong. Move on to the next topic.":pct>=50?"Solid base. Revise what you missed.":"Go back over this chapter, then try again.";',
' var h=\'<div class="dvqx-card" style="text-align:center"><p class="dvqx-meta">Answer key</p>\';',
' h+=\'<p class="dvqx-score">\'+s+\'<span>/\'+Q.questions.length+\'</span></p><p>\'+pct+\'% \\u2014 \'+v+\'</p>\';',
' h+=\'<div class="dvqx-sheet">\';',
' Q.questions.forEach(function(q,k){h+=\'<span class="dvqx-m \'+(picked[k]===q.answer_index?"ok":"no")+\'">\'+(k+1)+\'</span>\';});',
' h+=\'</div><div class="dvqx-nav"><button class="dvqx-btn" id="dvqx-rev">Review answers</button>\'+',
'    \'<button class="dvqx-btn solid" id="dvqx-again">Try again</button></div></div>\';',
' root.innerHTML=h;',
' document.getElementById("dvqx-rev").onclick=function(){done=false;i=0;draw();};',
' document.getElementById("dvqx-again").onclick=function(){picked={};i=0;done=false;draw();};',
'}',
'draw();',
'})();',
'<\/script>',
'</body>',
'</html>'
		].join('\n');
	}

	/* ── Export view ─────────────────────────────────────────────── */

	function openExport() {
		if (!state.quiz) { return false; }
		if (!state.html) { state.html = buildStandalone(state.quiz); }

		$('dvq-code').textContent = state.html;
		$('dvq-filesize').textContent =
			(new Blob([state.html]).size / 1024).toFixed(1) + ' KB';

		var copy = $('dvq-copy');
		copy.classList.remove('is-done');
		copy.textContent = 'Copy HTML code';

		setExportMode('code');
		showView('export');
		return true;
	}

	function setExportMode(mode) {
		$('dvq-codewrap').hidden = mode !== 'code';
		$('dvq-previewwrap').hidden = mode !== 'preview';

		root.querySelectorAll('#dvq-exp-toggle .dvq-seg').forEach(function (b) {
			b.classList.toggle('is-on', b.dataset.mode === mode);
		});

		if (mode === 'preview') { $('dvq-preview').srcdoc = state.html; }
	}

	root.querySelectorAll('#dvq-exp-toggle .dvq-seg').forEach(function (b) {
		b.addEventListener('click', function () { setExportMode(b.dataset.mode); });
	});

	root.querySelectorAll('#dvq-segment .dvq-seg').forEach(function (b) {
		b.addEventListener('click', function () {
			if (b.dataset.view === 'export') { openExport(); }
			else { showView(state.scored ? 'result' : 'paper'); }
		});
	});

	$('dvq-copy').addEventListener('click', function () {
		var btn = this;

		function done() {
			paintSteps(4);
			btn.classList.add('is-done');
			btn.textContent = 'Copied to clipboard';
			setTimeout(function () {
				btn.classList.remove('is-done');
				btn.textContent = 'Copy HTML code';
			}, 2400);
		}

		function fallback() {
			// The clipboard API needs HTTPS, so select the code for Ctrl+C instead.
			var range = document.createRange();
			range.selectNodeContents($('dvq-code'));
			var sel = window.getSelection();
			sel.removeAllRanges();
			sel.addRange(range);
			btn.textContent = 'Selected \u2014 press Ctrl+C';
		}

		if (navigator.clipboard && navigator.clipboard.writeText) {
			navigator.clipboard.writeText(state.html).then(done, fallback);
		} else {
			fallback();
		}
	});

	$('dvq-download').addEventListener('click', function () {
		saveBlob(state.html, 'text/html;charset=utf-8', slug(state.quiz.title) + '.html');
	});

	/* ── Navigation ──────────────────────────────────────────────── */

	$('dvq-review').addEventListener('click', function () {
		if ($('dvq-quiz').scrollIntoView) { $('dvq-quiz').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
	});

	$('dvq-print').addEventListener('click', function () { window.print(); });

	$('dvq-again').addEventListener('click', function () { renderQuiz(state.quiz); });

	function goBuilder() {
		state.quiz = null;
		state.answers = {};
		state.html = '';
		state.scored = false;
		$('dvq-questions').textContent = '';
		showView('builder');
	}

	$('dvq-back').addEventListener('click', goBuilder);

	// Paint the initial state rather than trusting the markup's attributes.
	showView('builder');
})();
