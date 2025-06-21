# Refactoring Prompt for Multiple AAA

## Issue Description
The test method contains multiple complete `<arrange,act,assert>` sequences, which violates the single responsibility principle. Each test method should verify only one specific behavior or scenario.

## Detection Pattern
- Multiple distinct arrange-act-assert cycles within a single test method
- Testing multiple scenarios or behaviors in one method
- Multiple independent assertions testing different aspects

## Refactoring Strategy
1. **Identify Distinct Scenarios**: Separate each complete arrange-act-assert sequence
2. **Extract Individual Tests**: Create separate test methods for each scenario
3. **Maintain Test Names**: Use descriptive names that reflect the specific behavior being tested
4. **Preserve All Logic**: Ensure no test logic is lost during the split

## Example Transformation

### Before:
```java
@Test
public void testUserOperations() {
    // First AAA sequence
    User user = new User("john");
    user.setEmail("john@example.com");
    assertEquals("john@example.com", user.getEmail());
    
    // Second AAA sequence
    User anotherUser = new User("jane");
    anotherUser.setAge(25);
    assertEquals(25, anotherUser.getAge());
}
```

### After:
```java
@Test
public void testUserEmailSetting() {
    // Arrange
    User user = new User("john");
    
    // Act
    user.setEmail("john@example.com");
    
    // Assert
    assertEquals("john@example.com", user.getEmail());
}

@Test
public void testUserAgeSetting() {
    // Arrange
    User user = new User("jane");
    
    // Act
    user.setAge(25);
    
    // Assert
    assertEquals(25, user.getAge());
}
```

## Important Considerations
- **Method Naming**: Each new test method should have a descriptive name indicating what specific behavior is being tested
- **Test Independence**: Ensure each split test method is completely independent
- **Shared Setup**: Consider using `@Before` methods if there's common setup code
- **Preserve Assertions**: Every assertion from the original test must be preserved in the appropriate split test

## Instructions for This Refactoring
Since this involves splitting a single method into multiple methods, focus on identifying the primary behavior being tested and refactor accordingly. If the test name suggests testing multiple operations, create the most important test method that captures the core functionality being verified.