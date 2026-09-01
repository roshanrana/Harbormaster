package web

import (
	"embed"
	"fmt"
	"html/template"
	"io"
	"io/fs"
)

// Templates and static assets are embedded into the binary. The console must
// render on a machine with no network access and no sidecar file server, which
// is the normal condition on a locked-down operations desktop.

//go:embed all:assets/templates
var templatesFS embed.FS

//go:embed all:assets/static
var staticFS embed.FS

// pages are the full-page templates. Each is parsed into its own template set
// alongside the shared layout and partials, because every page defines its own
// "content" block and a single flat set would let the last one parsed win.
var pages = []string{"board", "quarantine", "slots", "arrival"}

// shared templates are parsed into every set.
var shared = []string{"assets/templates/layout.html", "assets/templates/partials.html"}

// TemplateSet holds one parsed template per page.
type TemplateSet struct {
	sets map[string]*template.Template
}

// Templates parses the embedded template set.
func Templates() (*TemplateSet, error) {
	out := &TemplateSet{sets: make(map[string]*template.Template, len(pages))}
	for _, page := range pages {
		files := append([]string{}, shared...)
		files = append(files, fmt.Sprintf("assets/templates/%s.html", page))
		t, err := template.New(page).Funcs(TemplateFuncs()).ParseFS(templatesFS, files...)
		if err != nil {
			return nil, fmt.Errorf("web: parse %s: %w", page, err)
		}
		out.sets[page] = t
	}
	return out, nil
}

// ExecuteTemplate renders a page or a partial.
//
// Partials are rendered from the board set, which includes the shared partials
// file; they do not depend on any page-specific block.
func (ts *TemplateSet) ExecuteTemplate(w io.Writer, name string, data any) error {
	if t, ok := ts.sets[name]; ok {
		if err := t.ExecuteTemplate(w, name, data); err != nil {
			return fmt.Errorf("web: render %s: %w", name, err)
		}
		return nil
	}
	fallback, ok := ts.sets["board"]
	if !ok {
		return fmt.Errorf("web: no template named %q", name)
	}
	if err := fallback.ExecuteTemplate(w, name, data); err != nil {
		return fmt.Errorf("web: render partial %s: %w", name, err)
	}
	return nil
}

// StaticAssets returns the embedded CSS and script bundle.
func StaticAssets() (fs.FS, error) {
	sub, err := fs.Sub(staticFS, "assets/static")
	if err != nil {
		return nil, fmt.Errorf("web: static assets: %w", err)
	}
	return sub, nil
}
