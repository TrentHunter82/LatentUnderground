import { createContext, useContext } from 'react'

/**
 * App-chrome context — exposes the global project-list state (owned by App) to
 * deep descendants without prop-drilling through React-Router's <Routes>.
 *
 * This is what lets the dockable Navigator tile inside ProjectWorkspace reuse
 * the existing <Sidebar> (projects, health, archive filter, refresh) while the
 * sidebar is no longer rendered as fixed chrome on the project route.
 */
const AppChromeContext = createContext(null)

export function AppChromeProvider({ value, children }) {
  return <AppChromeContext.Provider value={value}>{children}</AppChromeContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAppChrome() {
  return useContext(AppChromeContext)
}
