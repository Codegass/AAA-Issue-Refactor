# Refactoring Prompt for Obscure Assert

## Issue Description
The test method contains assertion logic with high cyclomatic complexity (> 2), making it difficult to understand and maintain. Complex assertion logic often includes if/else statements, loops, or try-catch blocks that obscure the actual test verification.

## Detection Pattern
- Assertions containing if/else statements
- Loops within assertion logic
- Try-catch blocks in assertion code
- Complex conditional logic in assertions
- Nested or chained assertions with complex logic

## Refactoring Strategy
1. **Simplify Assertion Logic**: Replace complex logic with straightforward assertions
2. **Use Hamcrest Matchers**: Leverage Hamcrest for complex validations
3. **Extract Helper Methods**: Move complex verification logic to helper methods
4. **Multiple Simple Assertions**: Break complex assertions into multiple simple ones
5. **Use Appropriate Assertion Methods**: Choose the most suitable assertion for each check

## Example Transformation

### Before:
```java
@Test
public void testUserValidation() {
    List<User> users = userService.getAllUsers();
    
    // Obscure assertion with complex logic
    boolean isValid = true;
    for (User user : users) {
        if (user.getAge() < 18 || user.getEmail() == null) {
            isValid = false;
            break;
        }
        try {
            if (!user.getEmail().contains("@")) {
                isValid = false;
                break;
            }
        } catch (Exception e) {
            isValid = false;
            break;
        }
    }
    assertTrue("All users should be valid", isValid);
}
```

### After:
```java
@Test
public void testUserValidation() {
    List<User> users = userService.getAllUsers();
    
    // Clear, simple assertions
    assertThat(users, is(not(empty())));
    
    for (User user : users) {
        assertThat("User age should be 18 or older", user.getAge(), greaterThanOrEqualTo(18));
        assertThat("User email should not be null", user.getEmail(), is(notNullValue()));
        assertThat("User email should contain @", user.getEmail(), containsString("@"));
    }
}
```

## Hamcrest Matchers to Consider
- `is()`, `not()` - Basic matching
- `nullValue()`, `notNullValue()` - Null checks
- `empty()`, `hasSize()` - Collection checks
- `containsString()`, `startsWith()`, `endsWith()` - String checks
- `greaterThan()`, `lessThan()`, `equalTo()` - Numeric comparisons
- `hasItem()`, `hasItems()`, `contains()` - Collection content checks

## Alternative Approaches
1. **Multiple Assertions**: Break one complex assertion into several simple ones
2. **Helper Methods**: Extract complex validation logic into private helper methods
3. **Custom Matchers**: Create custom Hamcrest matchers for domain-specific validations
4. **Assert Methods**: Use specific assert methods like `assertThrows()` for exception cases

## Important Considerations
- **Readability**: Prioritize clear, readable assertions over clever one-liners
- **Failure Messages**: Provide clear failure messages for each assertion
- **Performance**: Consider performance implications of complex assertions in loops
- **Maintainability**: Ensure assertions are easy to understand and modify

## Instructions for This Refactoring
Identify the complex assertion logic and break it down into clear, simple assertions. Use Hamcrest matchers where appropriate to improve readability. If the logic is too complex, consider extracting it into helper methods with descriptive names. Ensure that all the original validation logic is preserved but in a more maintainable form.