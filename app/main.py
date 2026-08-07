import os, re, sys, json, shutil, subprocess, zipfile
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer, QProcessEnvironment
from PySide6.QtGui import QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QPainter, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox, QTabWidget, QToolBar, QStatusBar, QComboBox, QDialog, QListWidget, QListWidgetItem, QLineEdit, QTextEdit, QInputDialog, QCheckBox, QCompleter, QMenu, QFormLayout, QSpinBox, QDialogButtonBox
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView

APP_NAME = 'LaTeX Thesis Studio'
VERSION = '1.0.0'

LATEX_COMMANDS = sorted(set(r'''\documentclass \usepackage \begin \end \chapter \section \subsection \subsubsection \paragraph \label \ref \eqref \cite \parencite \textcite \autocite \footcite \include \input \includegraphics \caption \subcaption \centering \hfill \vspace \hspace \textbf \textit \emph \underline \url \href \item \tableofcontents \listoffigures \listoftables \printbibliography \addbibresource \author \title \date \maketitle \newcommand \renewcommand \setcounter \appendix \toprule \midrule \bottomrule \multirow'''.split()))

COMMON_PACKAGE_FILES = {
    'amsmath.sty':'amsmath','amssymb.sty':'amsfonts','graphicx.sty':'graphics','geometry.sty':'geometry',
    'fontspec.sty':'fontspec','polyglossia.sty':'polyglossia','biblatex.sty':'biblatex','csquotes.sty':'csquotes',
    'booktabs.sty':'booktabs','longtable.sty':'tools','tabularx.sty':'tools','multirow.sty':'multirow',
    'caption.sty':'caption','subcaption.sty':'caption','float.sty':'float','xcolor.sty':'xcolor','hyperref.sty':'hyperref',
    'microtype.sty':'microtype','setspace.sty':'setspace','titlesec.sty':'titlesec','tocloft.sty':'tocloft',
    'enumitem.sty':'enumitem','glossaries.sty':'glossaries','acro.sty':'acro','siunitx.sty':'siunitx','mathtools.sty':'mathtools'
}

def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

def runtime_bin():
    base = app_root()
    for p in (base/'runtime'/'TinyTeX'/'bin'/'windows', base/'runtime'/'TinyTeX'/'bin'/'win32'):
        if p.exists(): return p
    return None

def tool(name):
    rb = runtime_bin()
    if rb:
        for n in (name, name+'.exe', name+'.bat'):
            p=rb/n
            if p.exists(): return str(p)
    return shutil.which(name)

class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        def fmt(color,bold=False):
            f=QTextCharFormat(); f.setForeground(QColor(color));
            if bold: f.setFontWeight(700)
            return f
        self.rules=[(re.compile(r'\\[A-Za-z@]+'),fmt('#2f6fce',True)),(re.compile(r'%.*$'),fmt('#6a8759')),(re.compile(r'\$.*?\$'),fmt('#9b4f96')),(re.compile(r'[{}\[\]]'),fmt('#c26a00'))]
    def highlightBlock(self,text):
        for rx,f in self.rules:
            for m in rx.finditer(text): self.setFormat(m.start(),m.end()-m.start(),f)

class LineNumberArea(QWidget):
    def __init__(self, editor): super().__init__(editor); self.editor=editor
    def paintEvent(self,event): self.editor.paint_line_numbers(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self,path,parent=None):
        super().__init__(parent); self.path=Path(path); self.setLineWrapMode(QPlainTextEdit.NoWrap)
        f=QFont('Consolas',11); f.setStyleHint(QFont.Monospace); self.setFont(f)
        self.highlighter=LatexHighlighter(self.document()); self.line_area=LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_area_width); self.updateRequest.connect(self.update_line_area); self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_area_width(0); self.highlight_current_line()
        self.completer=QCompleter(LATEX_COMMANDS,self); self.completer.setCaseSensitivity(Qt.CaseInsensitive); self.completer.setWidget(self); self.completer.activated.connect(self.insert_completion)
    def line_number_width(self): return 12+self.fontMetrics().horizontalAdvance('9')*len(str(max(1,self.blockCount())))
    def update_line_area_width(self,_): self.setViewportMargins(self.line_number_width(),0,0,0)
    def resizeEvent(self,e):
        super().resizeEvent(e); cr=self.contentsRect(); self.line_area.setGeometry(cr.left(),cr.top(),self.line_number_width(),cr.height())
    def update_line_area(self,rect,dy):
        self.line_area.scroll(0,dy) if dy else self.line_area.update(0,rect.y(),self.line_area.width(),rect.height())
        if rect.contains(self.viewport().rect()): self.update_line_area_width(0)
    def paint_line_numbers(self,event):
        p=QPainter(self.line_area); p.fillRect(event.rect(),QColor('#f0f2f4')); block=self.firstVisibleBlock(); n=block.blockNumber(); top=round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top()); bottom=top+round(self.blockBoundingRect(block).height())
        while block.isValid() and top<=event.rect().bottom():
            if block.isVisible() and bottom>=event.rect().top(): p.setPen(QColor('#7b8188')); p.drawText(0,top,self.line_area.width()-6,self.fontMetrics().height(),Qt.AlignRight,str(n+1))
            block=block.next(); top=bottom; bottom=top+round(self.blockBoundingRect(block).height()); n+=1
    def highlight_current_line(self):
        x=QTextEdit.ExtraSelection(); x.format.setBackground(QColor('#f7f9fb')); x.format.setProperty(QTextCharFormat.FullWidthSelection,True); x.cursor=self.textCursor(); x.cursor.clearSelection(); self.setExtraSelections([x])
    def text_under_cursor(self):
        tc=self.textCursor(); tc.select(QTextCursor.WordUnderCursor); start=tc.selectionStart(); text=tc.selectedText()
        if start>0:
            t=QTextCursor(self.document()); t.setPosition(start-1); t.setPosition(start,QTextCursor.KeepAnchor)
            if t.selectedText()=='\\': text='\\'+text
        return text
    def keyPressEvent(self,e):
        if self.completer.popup().isVisible() and e.key() in (Qt.Key_Enter,Qt.Key_Return,Qt.Key_Escape,Qt.Key_Tab): e.ignore(); return
        if e.text() in ('{','[','('):
            pairs={'{':'}','[':']','(':')'}; super().keyPressEvent(e); self.insertPlainText(pairs[e.text()]); c=self.textCursor(); c.movePosition(QTextCursor.Left); self.setTextCursor(c); return
        super().keyPressEvent(e); prefix=self.text_under_cursor()
        if prefix.startswith('\\') and len(prefix)>=2: self.completer.setCompletionPrefix(prefix); cr=self.cursorRect(); cr.setWidth(300); self.completer.complete(cr)
        else: self.completer.popup().hide()
    def insert_completion(self,completion):
        tc=self.textCursor(); prefix=self.text_under_cursor()
        if prefix: tc.movePosition(QTextCursor.Left,QTextCursor.KeepAnchor,len(prefix))
        tc.insertText(completion); self.setTextCursor(tc)
    def goto_line(self,line):
        b=self.document().findBlockByLineNumber(max(0,line-1))
        if b.isValid(): self.setTextCursor(QTextCursor(b)); self.centerCursor(); self.setFocus()

class SearchDialog(QDialog):
    def __init__(self,root,opener,parent=None):
        super().__init__(parent); self.root=Path(root); self.opener=opener; self.setWindowTitle('Search in project'); self.resize(760,500)
        l=QVBoxLayout(self); row=QHBoxLayout(); self.q=QLineEdit(); self.q.setPlaceholderText('Search text...'); b=QPushButton('Search'); row.addWidget(self.q); row.addWidget(b); l.addLayout(row); self.results=QListWidget(); l.addWidget(self.results); b.clicked.connect(self.search); self.q.returnPressed.connect(self.search); self.results.itemDoubleClicked.connect(self.open_result)
    def search(self):
        self.results.clear(); q=self.q.text().lower()
        if not q: return
        for p in self.root.rglob('*'):
            if p.suffix.lower() not in {'.tex','.bib','.sty','.cls','.txt'}: continue
            try: lines=p.read_text(encoding='utf-8').splitlines()
            except Exception: continue
            for i,line in enumerate(lines,1):
                if q in line.lower(): it=QListWidgetItem(f'{p.relative_to(self.root)}:{i}  {line.strip()[:100]}'); it.setData(Qt.UserRole,(str(p),i)); self.results.addItem(it)
    def open_result(self,item): p,line=item.data(Qt.UserRole); self.opener(Path(p),line); self.accept()

class SettingsDialog(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent); self.setWindowTitle('Settings'); f=QFormLayout(self); self.autosave=QSpinBox(); self.autosave.setRange(2,300); self.autosave.setValue(settings.get('autosave_seconds',10)); self.autocompile=QCheckBox(); self.autocompile.setChecked(settings.get('auto_compile',False)); self.install=QCheckBox(); self.install.setChecked(settings.get('auto_install_packages',True)); f.addRow('Auto-save every (seconds)',self.autosave); f.addRow('Auto compile after save',self.autocompile); f.addRow('Offer missing package installation',self.install); bb=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); f.addRow(bb); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
    def result_settings(self): return {'autosave_seconds':self.autosave.value(),'auto_compile':self.autocompile.isChecked(),'auto_install_packages':self.install.isChecked()}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.project_dir=None; self.main_tex=None; self.open_editors={}; self.proc=None; self.settings_path=Path.home()/'.latex_thesis_studio.json'; self.settings=self.load_settings(); self.pdf_doc=QPdfDocument(self); self.build_ui(); self.apply_style(); self.timer=QTimer(self); self.timer.timeout.connect(self.autosave); self.reset_timer()
    def load_settings(self):
        d={'autosave_seconds':10,'auto_compile':False,'auto_install_packages':True}
        try: d.update(json.loads(self.settings_path.read_text(encoding='utf-8')))
        except Exception: pass
        return d
    def save_settings_file(self): self.settings_path.write_text(json.dumps(self.settings,indent=2),encoding='utf-8')
    def reset_timer(self): self.timer.start(max(2,int(self.settings['autosave_seconds']))*1000)
    def build_ui(self):
        self.resize(1600,950); self.setWindowTitle(APP_NAME); tb=QToolBar(); tb.setMovable(False); self.addToolBar(tb)
        for text,fn in [('New',self.new_project),('Open',self.open_project),('Import ZIP',self.import_zip),('Save',self.save_current),('Save All',self.save_all),('Compile',self.compile),('Stop',self.stop_compile),('Search',self.search_project),('Export ZIP',self.export_zip),('Settings',self.open_settings)]:
            a=QAction(text,self); a.triggered.connect(fn); tb.addAction(a)
            if text in {'Open','Save All','Stop','Search'}: tb.addSeparator()
        tb.addWidget(QLabel(' Engine: ')); self.engine=QComboBox(); self.engine.addItems(['latexmk + XeLaTeX','XeLaTeX','LuaLaTeX']); tb.addWidget(self.engine); self.status=QStatusBar(); self.setStatusBar(self.status)
        h=QSplitter(Qt.Horizontal); left=QWidget(); ll=QVBoxLayout(left); ll.setContentsMargins(5,5,5,5); ll.addWidget(QLabel('PROJECT')); self.tree=QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.itemDoubleClicked.connect(self.open_tree); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.tree_menu); ll.addWidget(self.tree); h.addWidget(left)
        self.tabs=QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.tabCloseRequested.connect(self.close_tab); h.addWidget(self.tabs)
        right=QWidget(); rl=QVBoxLayout(right); rr=QHBoxLayout(); rr.addWidget(QLabel('PDF PREVIEW')); rr.addStretch(); reload=QPushButton('Reload'); reload.clicked.connect(self.load_pdf); rr.addWidget(reload); rl.addLayout(rr); self.pdf=QPdfView(); self.pdf.setDocument(self.pdf_doc); self.pdf.setPageMode(QPdfView.PageMode.MultiPage); self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth); rl.addWidget(self.pdf); h.addWidget(right); h.setSizes([240,700,600])
        v=QSplitter(Qt.Vertical); v.addWidget(h); self.console=QPlainTextEdit(); self.console.setReadOnly(True); self.console.setFont(QFont('Consolas',9)); self.console.mouseDoubleClickEvent=self.console_double_click; v.addWidget(self.console); v.setSizes([760,180]); self.setCentralWidget(v)
        QShortcut(QKeySequence('Ctrl+S'),self,self.save_current); QShortcut(QKeySequence('Ctrl+B'),self,self.compile); QShortcut(QKeySequence('Ctrl+Shift+F'),self,self.search_project)
    def apply_style(self): self.setStyleSheet('QMainWindow{background:#eef1f4} QToolBar{background:white;border-bottom:1px solid #d8dde2;padding:5px;spacing:4px} QTreeWidget,QPlainTextEdit,QPdfView,QTabWidget::pane{background:white;border:1px solid #d7dce1} QPushButton{background:#138a5b;color:white;border:0;padding:6px 10px;border-radius:4px} QPushButton:hover{background:#0f744c} QComboBox,QLineEdit,QSpinBox{background:white;padding:5px;border:1px solid #cfd5da;border-radius:4px}')
    def new_project(self):
        parent=QFileDialog.getExistingDirectory(self,'Choose project location')
        if not parent: return
        name,ok=QInputDialog.getText(self,'Project name','Name:',text='ThesisProject')
        if not ok or not name: return
        p=Path(parent)/name; (p/'chapters').mkdir(parents=True,exist_ok=True); (p/'figures').mkdir(exist_ok=True); (p/'main.tex').write_text(TEMPLATE_MAIN,encoding='utf-8'); (p/'chapters'/'chapter1.tex').write_text(TEMPLATE_CH1,encoding='utf-8'); (p/'references.bib').write_text(TEMPLATE_BIB,encoding='utf-8'); self.load_project(p)
    def open_project(self):
        p=QFileDialog.getExistingDirectory(self,'Open LaTeX project')
        if p: self.load_project(Path(p))
    def load_project(self,p):
        self.project_dir=Path(p); candidates=[self.project_dir/'main.tex']+list(self.project_dir.glob('*.tex')); self.main_tex=next((x for x in candidates if x.exists()),None); self.refresh_tree();
        if self.main_tex: self.open_file(self.main_tex); self.load_pdf()
        self.setWindowTitle(f'{APP_NAME} — {self.project_dir.name}')
    def refresh_tree(self):
        self.tree.clear()
        if not self.project_dir: return
        root=QTreeWidgetItem([self.project_dir.name]); root.setData(0,Qt.UserRole,str(self.project_dir)); self.tree.addTopLevelItem(root); self.add_children(root,self.project_dir); root.setExpanded(True)
    def add_children(self,parent,p):
        ignored={'.git','__pycache__','build','dist','.vs'}; generated={'.aux','.log','.out','.toc','.bcf','.blg','.bbl','.fdb_latexmk','.fls'}
        for x in sorted(p.iterdir(),key=lambda z:(not z.is_dir(),z.name.lower())):
            if x.name in ignored or x.suffix.lower() in generated: continue
            it=QTreeWidgetItem([x.name]); it.setData(0,Qt.UserRole,str(x)); parent.addChild(it)
            if x.is_dir(): self.add_children(it,x)
    def open_tree(self,item,_):
        p=Path(item.data(0,Qt.UserRole))
        if p.is_file() and p.suffix.lower() in {'.tex','.bib','.sty','.cls','.txt','.log'}: self.open_file(p)
    def tree_menu(self,pos):
        item=self.tree.itemAt(pos); menu=QMenu(self)
        if item:
            p=Path(item.data(0,Qt.UserRole))
            if p.is_dir():
                a=menu.addAction('New .tex file'); chosen=menu.exec(self.tree.viewport().mapToGlobal(pos))
                if chosen==a:
                    name,ok=QInputDialog.getText(self,'New file','Filename:',text='chapter.tex')
                    if ok and name: (p/name).write_text('',encoding='utf-8'); self.refresh_tree()
                return
        menu.addAction('Refresh',self.refresh_tree); menu.exec(self.tree.viewport().mapToGlobal(pos))
    def open_file(self,p,line=None):
        key=str(p.resolve())
        if key in self.open_editors: e=self.open_editors[key]
        else:
            e=CodeEditor(p)
            try: e.setPlainText(p.read_text(encoding='utf-8'))
            except Exception: e.setPlainText(p.read_text(errors='replace'))
            self.open_editors[key]=e; self.tabs.addTab(e,p.name)
        self.tabs.setCurrentWidget(e)
        if line: e.goto_line(line)
    def close_tab(self,i):
        e=self.tabs.widget(i)
        if isinstance(e,CodeEditor): self.save_editor(e); self.open_editors.pop(str(e.path.resolve()),None)
        self.tabs.removeTab(i)
    def save_editor(self,e): e.path.write_text(e.toPlainText(),encoding='utf-8')
    def save_current(self):
        e=self.tabs.currentWidget()
        if isinstance(e,CodeEditor): self.save_editor(e); self.status.showMessage('Saved',1500)
    def save_all(self):
        for e in self.open_editors.values(): self.save_editor(e)
    def autosave(self):
        if self.open_editors:
            self.save_all()
            if self.settings.get('auto_compile') and (not self.proc or self.proc.state()==QProcess.NotRunning): self.compile()
    def build_environment(self):
        env=os.environ.copy(); rb=runtime_bin()
        if rb: env['PATH']=str(rb)+os.pathsep+env.get('PATH','')
        return env
    def compile_command(self):
        if self.engine.currentIndex()==0:
            exe=tool('latexmk'); return [exe,'-xelatex','-interaction=nonstopmode','-file-line-error','-synctex=1',self.main_tex.name] if exe else None
        if self.engine.currentIndex()==1:
            exe=tool('xelatex'); return [exe,'-interaction=nonstopmode','-file-line-error','-synctex=1',self.main_tex.name] if exe else None
        exe=tool('lualatex'); return [exe,'-interaction=nonstopmode','-file-line-error','-synctex=1',self.main_tex.name] if exe else None
    def compile(self):
        if not self.main_tex: QMessageBox.warning(self,'No project','Open a project first.'); return
        self.save_all(); cmd=self.compile_command()
        if not cmd: QMessageBox.critical(self,'Bundled LaTeX runtime missing','The built-in TinyTeX runtime was not found. Build the self-contained Windows release using the supplied builder.'); return
        if self.proc and self.proc.state()!=QProcess.NotRunning: return
        self.console.clear(); self.console.appendPlainText('$ '+' '.join(cmd)); self.proc=QProcess(self); self.proc.setWorkingDirectory(str(self.project_dir)); qenv=QProcessEnvironment.systemEnvironment();
        for k,v in self.build_environment().items(): qenv.insert(k,v)
        self.proc.setProcessEnvironment(qenv); self.proc.setProgram(cmd[0]); self.proc.setArguments(cmd[1:]); self.proc.setProcessChannelMode(QProcess.MergedChannels); self.proc.readyReadStandardOutput.connect(self.read_output); self.proc.finished.connect(self.compile_finished); self.proc.start(); self.status.showMessage('Compiling...')
    def read_output(self): self.console.insertPlainText(bytes(self.proc.readAllStandardOutput()).decode(errors='replace')); self.console.ensureCursorVisible()
    def compile_finished(self,code,_):
        text=self.console.toPlainText(); self.status.showMessage('Compilation successful' if code==0 else 'Compilation failed',4000)
        if code==0: self.load_pdf()
        missing=sorted(set(re.findall(r"(?:LaTeX Error: File|I can't find file)\s*[`']([^`']+)[`']",text)))
        if missing and self.settings.get('auto_install_packages',True): self.handle_missing(missing)
    def handle_missing(self,files):
        if not tool('tlmgr'): QMessageBox.warning(self,'Missing packages','Missing: '+', '.join(files)); return
        msg='Missing LaTeX files:\n• '+'\n• '.join(files)+'\n\nInstall the required package(s) now from CTAN?'
        if QMessageBox.question(self,'Install missing packages?',msg)==QMessageBox.Yes: self.install_packages(files)
    def install_packages(self,files):
        tlmgr=tool('tlmgr'); pkgs=set()
        for f in files:
            if f in COMMON_PACKAGE_FILES: pkgs.add(COMMON_PACKAGE_FILES[f]); continue
            try:
                r=subprocess.run([tlmgr,'search','--global','--file',f'/{f}'],capture_output=True,text=True,env=self.build_environment(),timeout=45)
                for line in r.stdout.splitlines():
                    if line and ':' in line and not line.startswith(('tlmgr:','http')):
                        pkg=line.split(':',1)[0].strip()
                        if pkg and ' ' not in pkg: pkgs.add(pkg); break
            except Exception: pass
        if not pkgs: QMessageBox.warning(self,'Package search','Could not determine the package automatically.'); return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r=subprocess.run([tlmgr,'install',*sorted(pkgs)],capture_output=True,text=True,env=self.build_environment(),timeout=600); self.console.appendPlainText('\n'+r.stdout+'\n'+r.stderr)
            if r.returncode==0: QMessageBox.information(self,'Packages installed','Installed successfully. Recompiling now.'); self.compile()
            else: QMessageBox.warning(self,'Installation failed','See the build console for details.')
        finally: QApplication.restoreOverrideCursor()
    def stop_compile(self):
        if self.proc and self.proc.state()!=QProcess.NotRunning: self.proc.kill()
    def load_pdf(self):
        if not self.main_tex: return
        p=self.main_tex.with_suffix('.pdf')
        if p.exists(): self.pdf_doc.close(); self.pdf_doc.load(str(p))
    def console_double_click(self,event):
        c=self.console.cursorForPosition(event.position().toPoint()); c.select(QTextCursor.LineUnderCursor); line=c.selectedText(); m=re.search(r'([^:\s]+\.tex):(\d+):',line)
        if m:
            p=(self.project_dir/m.group(1)).resolve()
            if p.exists(): self.open_file(p,int(m.group(2))); return
        QPlainTextEdit.mouseDoubleClickEvent(self.console,event)
    def search_project(self):
        if self.project_dir: SearchDialog(self.project_dir,self.open_file,self).exec()
    def import_zip(self):
        z=QFileDialog.getOpenFileName(self,'Import Overleaf ZIP','','ZIP files (*.zip)')[0]
        if not z: return
        parent=QFileDialog.getExistingDirectory(self,'Extract project to')
        if not parent: return
        dest=Path(parent)/Path(z).stem; dest.mkdir(exist_ok=True)
        with zipfile.ZipFile(z) as a: a.extractall(dest)
        children=list(dest.iterdir())
        if len(children)==1 and children[0].is_dir() and not (dest/'main.tex').exists(): dest=children[0]
        self.load_project(dest)
    def export_zip(self):
        if not self.project_dir: return
        out=QFileDialog.getSaveFileName(self,'Export project ZIP',str(self.project_dir.with_suffix('.zip')),'ZIP (*.zip)')[0]
        if not out: return
        self.save_all(); generated={'.aux','.log','.out','.toc','.bcf','.blg','.fdb_latexmk','.fls'}
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as a:
            for p in self.project_dir.rglob('*'):
                if p.is_file() and p.suffix.lower() not in generated: a.write(p,p.relative_to(self.project_dir))
        self.status.showMessage('Project exported',3000)
    def open_settings(self):
        d=SettingsDialog(self.settings,self)
        if d.exec()==QDialog.Accepted: self.settings.update(d.result_settings()); self.save_settings_file(); self.reset_timer()

TEMPLATE_MAIN=r'''\documentclass[12pt,a4paper,oneside]{report}
\usepackage{fontspec}
\usepackage{polyglossia}
\setdefaultlanguage{english}
\setotherlanguage{arabic}
\setmainfont{TeX Gyre Termes}
\newfontfamily\arabicfont[Script=Arabic]{Arial}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{setspace}\onehalfspacing
\usepackage{microtype}
\usepackage{graphicx}\graphicspath{{figures/}}
\usepackage{amsmath,amssymb,mathtools}
\usepackage{booktabs,longtable,tabularx,array,multirow}
\usepackage{caption,subcaption,float}
\usepackage{xcolor,csquotes}
\usepackage[hidelinks]{hyperref}
\usepackage[backend=biber,style=apa]{biblatex}
\addbibresource{references.bib}
\begin{document}
\begin{titlepage}\centering
{\Large University Name\par}\vspace{1.5cm}
{\LARGE\bfseries Thesis Title\par}\vfill
{\large Student Name\par}{\large 2026\par}
\end{titlepage}
\tableofcontents
\listoffigures
\listoftables
\include{chapters/chapter1}
\printbibliography
\end{document}
'''
TEMPLATE_CH1=r'''\chapter{Introduction}
\section{Background}
Write your thesis text here.
\section{Research Problem}
Describe the research problem.
\section{Objectives}
\begin{enumerate}
\item First objective.
\item Second objective.
\end{enumerate}
'''
TEMPLATE_BIB=r'''@article{example2026,
 author={Example, A.},
 title={Example reference},
 journal={Example Journal},
 year={2026},
 volume={1},
 number={1},
 pages={1--10}
}
'''

if __name__=='__main__':
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); w=MainWindow(); w.show(); sys.exit(app.exec())
