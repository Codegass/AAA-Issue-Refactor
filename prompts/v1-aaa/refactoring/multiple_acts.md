# Refactoring Prompt for Multiple Acts

## Issue Description
The test method follows an `<arrange,act1,act2,...,actn,assert>` pattern with sequential dependent actions before the final assertion. This pattern typically only verifies the result of the final action, potentially missing issues with intermediate actions.

## Detection Pattern
- Multiple sequential actions (method calls, operations) in the act phase
- Actions are dependent on each other (output of act1 feeds into act2)
- Only the final action's result is typically verified
- Test name explicitly indicates testing multiple operations

## Refactoring Strategy
1. **Analyze Action Dependencies**: Understand how actions relate to each other
2. **Determine Test Intent**: Check if the test truly needs to test multiple operations
3. **Consider Splitting**: If testing independent operations, split into separate tests
4. **Add Intermediate Verification**: If multiple actions are necessary, verify intermediate results
5. **Clarify Test Purpose**: Ensure the test name reflects what's actually being tested

## Example Transformation

### Before:
```java
@Test
public void testDataProcessingPipeline() {
    // Arrange
    RawData data = new RawData("input");
    DataProcessor processor = new DataProcessor();
    
    // Multiple Acts - only final result verified
    CleanedData cleaned = processor.cleanData(data);        // act1
    ValidatedData validated = processor.validateData(cleaned); // act2
    ProcessedData result = processor.processData(validated);   // act3
    
    // Assert - only final result checked
    assertEquals("processed", result.getValue());
}
```

### After:
```java
@Test
public void testDataProcessingPipeline() {
    // Arrange
    RawData data = new RawData("input");
    DataProcessor processor = new DataProcessor();
    
    // Act with intermediate verification
    CleanedData cleaned = processor.cleanData(data);
    assertNotNull("Data cleaning should not return null", cleaned);
    assertTrue("Cleaned data should be valid", cleaned.isValid());
    
    ValidatedData validated = processor.validateData(cleaned);
    assertNotNull("Data validation should not return null", validated);
    assertTrue("Validated data should pass validation", validated.isValidated());
    
    ProcessedData result = processor.processData(validated);
    
    // Assert - final result
    assertNotNull("Final processing should not return null", result);
    assertEquals("processed", result.getValue());
}
```

## Alternative Approaches

### Option 1: Split into Separate Tests
If actions are independent, create separate focused tests:
```java
@Test
public void testDataCleaning() { /* test only cleaning */ }

@Test
public void testDataValidation() { /* test only validation */ }

@Test
public void testDataProcessing() { /* test only processing */ }
```

### Option 2: Test the Pipeline as Integration Test
If the pipeline is the actual feature being tested:
```java
@Test
public void testCompleteDataProcessingPipeline() {
    // Test the entire pipeline with verification at each step
}
```

## Important Considerations
- **Test Purpose**: Determine if you're testing individual operations or an integrated pipeline
- **Error Propagation**: Consider how errors in early actions affect later actions
- **Intermediate State**: Verify important intermediate states if they matter for the test
- **Test Name**: Ensure the test name accurately reflects what's being tested
- **Single Responsibility**: Each test should have a clear, single purpose

## When Multiple Acts Are Appropriate
- Testing integrated workflows or pipelines
- Testing stateful operations where order matters
- Testing composite operations that naturally belong together
- Integration tests that verify component interactions

## Instructions for This Refactoring
Analyze whether the multiple actions represent a single logical operation (like a pipeline) or multiple independent operations. If it's a true pipeline test, add intermediate verifications to ensure each step works correctly. If the test name suggests testing multiple independent operations, focus on the primary operation indicated by the test name and ensure it's properly verified.