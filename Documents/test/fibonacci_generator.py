import os

def generate_fibonacci(n):
    fib_sequence = []
    a, b = 0, 1
    for _ in range(n):
        fib_sequence.append(a)
        a, b = b, a + b
    return fib_sequence

# Ensure the directory exists
directory = "Documents/test"
os.makedirs(directory, exist_ok=True)

# Generate and save Fibonacci numbers
file_path = os.path.join(directory, "fibonacci_numbers.txt")
with open(file_path, "w") as file:
    fib_numbers = generate_fibonacci(10)  # Generate first 10 Fibonacci numbers
    for number in fib_numbers:
        file.write(f"{number}\n")

print(f"Fibonacci numbers saved to {file_path}")