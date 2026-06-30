## MODIFIED Requirements

### Requirement: Provide an interactive terminal UI
The system SHALL provide a curses-based TUI for selecting a main project and optional additional projects.

#### Scenario: Navigating the tree
- **WHEN** the TUI is open
- **THEN** arrow keys or `j`/`k` move the selection
- **AND** right arrow expands a tree node
- **AND** left arrow collapses a tree node

#### Scenario: Scrolling downward through a long tree
- **WHEN** the current selection reaches the bottom visible row of a tree list that exceeds the viewport height
- **THEN** pressing Down or `j` SHALL keep the highlighted row visible
- **AND** the launcher SHALL scroll the tree upward by one row to reveal the next item

#### Scenario: Scrolling upward through a shifted tree
- **WHEN** the tree has been scrolled upward and the current selection reaches the top visible row
- **THEN** pressing Up or `k` SHALL keep the highlighted row visible
- **AND** the launcher SHALL scroll the tree downward by one row to reveal the previous item

#### Scenario: Managing selections
- **WHEN** the user presses `Enter`
- **THEN** the current item becomes the main project

#### Scenario: Marking additional projects
- **WHEN** the user presses `Space`
- **THEN** the current item cycles between unselected, additional, and main according to current selection state

#### Scenario: Launching from the TUI
- **WHEN** the user double-presses `Enter`, presses `F5`, or presses `r`
- **THEN** the launcher returns the selected main project and additional projects for execution
