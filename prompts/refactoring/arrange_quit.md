# Refactoring Prompt for Arrange & Quit

## Issue Description
The test method follows an `<arrange,if(condition)return,act,assert>` pattern where it silently returns (quits) if certain preconditions are not met. This prevents the test from running when conditions aren't ideal, but doesn't properly communicate why the test was skipped.

## Detection Pattern
- Early return statements based on conditional checks
- `if (condition) return;` statements after arrange phase
- Silent test termination without proper test skipping mechanism
- Tests that sometimes don't execute their main logic

## Refactoring Strategy
1. **Identify Early Return Conditions**: Find the conditions that cause early returns
2. **Convert to Assumptions**: Replace early return with `Assume.assumeXXX()` methods
3. **Proper Test Skipping**: Use JUnit's assumption mechanism for test skipping
4. **Clear Intent**: Make it clear when and why tests are skipped

## Example Transformation

### Before:
```java
@Test
public void testFileProcessing() {
    // Arrange
    File inputFile = new File("test-data.txt");
    FileProcessor processor = new FileProcessor();
    
    // Early return if file doesn't exist (WRONG!)
    if (!inputFile.exists()) {
        return; // Silent quit
    }
    
    // Act
    ProcessResult result = processor.processFile(inputFile);
    
    // Assert
    assertTrue(result.isSuccess());
    assertEquals(10, result.getProcessedCount());
}
```

### After:
```java
@Test
public void testFileProcessing() {
    // Arrange
    File inputFile = new File("test-data.txt");
    FileProcessor processor = new FileProcessor();
    
    // Use assumption instead of early return (CORRECT!)
    Assume.assumeTrue("Test file must exist", inputFile.exists());
    
    // Act
    ProcessResult result = processor.processFile(inputFile);
    
    // Assert
    assertTrue(result.isSuccess());
    assertEquals(10, result.getProcessedCount());
}
```

## Assume API Usage
- `Assume.assumeTrue(message, condition)` - Skip if condition is false
- `Assume.assumeFalse(message, condition)` - Skip if condition is true
- `Assume.assumeNotNull(message, object)` - Skip if object is null
- `Assume.assumeThat(message, actual, matcher)` - Skip if matcher doesn't match

## Benefits of Using Assumptions
- **Test Visibility**: Skipped tests are reported as skipped, not ignored
- **Clear Intent**: Makes it clear why tests were skipped
- **Better Reporting**: Test runners show skipped tests with reasons
- **Debugging Aid**: Helps identify environment or setup issues

## Common Early Return Scenarios
- File or resource existence checks
- Database connection availability
- Environment variable checks
- System capability verification
- Test data availability

## Important Considerations
- **Descriptive Messages**: Always provide clear messages explaining why tests are skipped
- **Import Statements**: Add `import org.junit.Assume;` if needed
- **Test Design**: Consider if frequently skipped tests indicate design problems
- **CI/CD Impact**: Understand how skipped tests affect your build pipeline

## Instructions for This Refactoring
Replace all early return statements with appropriate `Assume.assumeXXX()` calls. Ensure each assumption has a clear, descriptive message explaining the precondition. The test logic after the assumption should remain exactly the same - only the early return mechanism changes.