// How the page shows Markdown it did not write -- an agent's, a flow's: marked turns it into
// HTML, GitHub's flavour with its tables and its line breaks, and DOMPurify keeps of that only
// what cannot run, restyle the page or reach beyond it. Bundled by build.mjs into
// ../static/vendor/markdown.js.

import DOMPurify from 'dompurify';
import { Marked } from 'marked';

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (one) => ESCAPES[one]);

const OPTIONS = { gfm: true, breaks: true, async: false };
const marked = new Marked(OPTIONS);
// The same, with the HTML a message carries drawn as the text it is.
const text = new Marked(OPTIONS);

// A path on the machine the run happens on is not a link the browser can follow, and the
// sanitizer would keep its words but drop its address: drawn as the path it is instead, before
// there is an address to drop. Every caller of the renderer gets it.
const link = ({ href }) => {
  if (typeof href !== 'string' || !/^file:/i.test(href)) return false;
  const path = escapeHtml(href);
  return `<code title="${path}">${path}</code>`;
};

marked.use({ renderer: { link } });
text.use({
  renderer: {
    link,
    html: ({ text: raw }) => escapeHtml(raw),
  },
});

// A private copy, so that its hooks are this module's alone.
const purify = DOMPurify(globalThis.window);

purify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.hasAttribute('href')) {
    if (/^(https?|mailto):/i.test(node.getAttribute('href'))) {
      // A link opens beside the page, which it can neither reach back into nor name.
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer');
    } else {
      // One into the page itself (`#x`, `/rpc`) would move or reach the page: its words stay.
      node.removeAttribute('href');
    }
  } else if (node.tagName === 'INPUT') {
    // A task list's box shows whether it is ticked, and nothing else is an input here.
    if (node.getAttribute('type') === 'checkbox') node.setAttribute('disabled', '');
    else node.remove();
  } else if (node.tagName === 'IMG' && !/^data:image\//i.test(node.getAttribute('src') ?? '')) {
    // Only a picture carried inline is shown: any other would be fetched from somewhere, which
    // the page may not reach. Its words stand in for it.
    node.replaceWith(node.ownerDocument.createTextNode(node.getAttribute('alt') ?? ''));
  }
});

const SANITIZE = {
  USE_PROFILES: { html: true },
  // Nothing that restyles the page, takes input, or embeds another document.
  // Media other than an inline picture would be fetched, so it goes too.
  FORBID_TAGS: [
    'style', 'form', 'button', 'textarea', 'select', 'option', 'iframe', 'object', 'embed',
    'video', 'audio', 'source', 'track', 'picture',
  ],
  FORBID_ATTR: ['style', 'class', 'id', 'srcset', 'poster', 'background'],
};

/**
 * `md` as HTML that is safe to set as an element's `innerHTML`.
 *
 * @param {unknown} md What was written.
 * @param {{html?: 'markup'|'text'}} [options] `text` draws the HTML a message carries as its
 *   text, rather than as tags the sanitizer would keep or drop; the default keeps it markup.
 */
export function render(md, { html = 'markup' } = {}) {
  // Without a document DOMPurify would hand the HTML back as it came: refuse instead.
  if (!purify.isSupported) throw new Error('markdown.js renders only where there is a document');
  const parser = html === 'text' ? text : marked;
  return purify.sanitize(parser.parse(String(md ?? '')), SANITIZE);
}
