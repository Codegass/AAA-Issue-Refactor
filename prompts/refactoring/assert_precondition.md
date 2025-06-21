# Refactoring Prompt for Assert Pre-condition

## Issue Description
The test method follows an `<arrange,assert,act,assert>` pattern where assertions are used to verify preconditions before the main action. This misuses the assertion mechanism - preconditions should be verified using the Assume API, not assertions.

## Detection Pattern
- Assertions appear before the main action being tested
- Assertions verify setup state or preconditions
- The pattern includes both precondition assertions and actual test assertions

## Refactoring Strategy
1. **Identify Precondition Assertions**: Find assertions that verify setup rather than test outcomes
2. **Convert to Assumptions**: Replace precondition assertions with appropriate `Assume.assumeXXX()` methods
3. **Preserve Test Assertions**: Keep the real test assertions that verify the expected behavior
4. **Add Imports**: Add `import org.junit.Assume;` if needed

## Example Transformation

### Before:
```java
@Test
public void testUserDeletion() {
    // Arrange
    User user = userRepository.findById(1L);
    
    // Assert (precondition - WRONG!)
    assertNotNull(user);
    assertTrue(user.isActive());
    
    // Act
    userService.deleteUser(user.getId());
    
    // Assert (actual test)
    assertFalse(userRepository.existsById(1L));
}
```

### After:
```java
@Test
public void testUserDeletion() {
    // Arrange
    User user = userRepository.findById(1L);
    
    // Assume (precondition - CORRECT!)
    Assume.assumeNotNull(user);
    Assume.assumeTrue(user.isActive());
    
    // Act
    userService.deleteUser(user.getId());
    
    // Assert (actual test)
    assertFalse(userRepository.existsById(1L));
}
```

## Assume API Methods
- `Assume.assumeTrue(condition)` - Skip test if condition is false
- `Assume.assumeFalse(condition)` - Skip test if condition is true
- `Assume.assumeNotNull(object)` - Skip test if object is null
- `Assume.assumeThat(actual, matcher)` - Skip test if matcher doesn't match

## Important Considerations
- **Test Skipping**: Assumptions cause tests to be skipped (not failed) when conditions aren't met
- **Precondition vs Assertion**: Preconditions verify test setup; assertions verify test outcomes
- **Import Statements**: Add `import org.junit.Assume;` if not already present
- **Test Validity**: Ensure the main test logic remains intact after converting preconditions

## When to Use Assumptions
- Verifying test data exists before testing
- Checking system state before running tests
- Validating environment conditions
- Ensuring objects are in expected states before testing

## Instructions for This Refactoring
Carefully distinguish between precondition checks (which should become assumptions) and actual test verification (which should remain as assertions). Convert only the precondition assertions to assumptions while preserving all test logic and actual test assertions.