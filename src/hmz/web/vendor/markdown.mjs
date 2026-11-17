// How the page shows Markdown it did not write -- an agent's, a flow's: marked turns it into
// HTML, GitHub's flavour with its tables, and DOMPurify keeps of that only what cannot run,
// restyle the page or reach beyond it. Bundled by build.mjs into ../static/vendor/markdown.js.

import DOMPurify from 'dompurify';
import { Marked } from 'marked';

const marked = new Marked({ gfm: true, breaks: false, async: false });

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

/** `md` as HTML that is safe to set as an element's `innerHTML`. */
export function render(md) {
  // Without a document DOMPurify would hand the HTML back as it came: refuse instead.
  if (!purify.isSupported) throw new Error('markdown.js renders only where there is a document');
  return purify.sanitize(marked.parse(String(md ?? '')), SANITIZE);
}
