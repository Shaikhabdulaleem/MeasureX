/// Render a package number for display (PRD §10 rule 2). Before the server
/// assigns the final number, the provisional number is shown with a trailing
/// asterisk, e.g. "PKG 02*"; once synced the server number is shown plainly.
String formatPackageLabel({int? serverNumber, required int provisionalNumber}) {
  if (serverNumber != null) {
    return 'PKG ${_two(serverNumber)}';
  }
  return 'PKG ${_two(provisionalNumber)}*';
}

String _two(int n) => n.toString().padLeft(2, '0');
