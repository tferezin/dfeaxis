export function AppFooter() {
  return (
    <footer className="border-t bg-muted/30 px-6 py-3 text-xs text-muted-foreground flex items-center justify-between">
      <span>Developed by <strong>DFeAxis</strong></span>
      <span>&copy; {new Date().getFullYear()} DFeAxis. Todos os direitos reservados.</span>
    </footer>
  )
}
