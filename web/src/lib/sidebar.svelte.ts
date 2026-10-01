// Whether the sidebar shows labels or only icons. Kept per browser; storage can be unavailable.
const KEY = "lo9i.sidebar";

class Sidebar {
  collapsed = $state(read());

  toggle(): void {
    this.collapsed = !this.collapsed;
    try {
      localStorage.setItem(KEY, this.collapsed ? "collapsed" : "open");
    } catch {
      // Kept for this page only.
    }
  }
}

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "collapsed";
  } catch {
    return false;
  }
}

export const sidebar = new Sidebar();
