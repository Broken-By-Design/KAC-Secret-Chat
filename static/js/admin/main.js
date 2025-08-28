// Creates the main application object if it doesn't exist.
var AdminPanel = window.AdminPanel || {};

document.addEventListener("DOMContentLoaded", function () {
    const usersListElement = document.querySelector("#usersList ul");
    const selectedUsersTitle = document.querySelector(".actions_container h1");
    const refreshBtn = document.getElementById("refreshBtn");
    const kickBtn = document.getElementById("kickBtn"); // Assuming this is the kick button

    // Global commands
    const resetChatBtn = document.getElementById("resetChatBtn");
    const reloadAllUsersBtn = document.getElementById("reloadAllUsersBtn");
    const cloakAllUsersBtn = document.getElementById("cloakAllUsersBtn");

    // troll Commands, LOLz
    const jumpscareBtn = document.getElementById("jumpscareBtn");
    const crashBtn = document.getElementById("crashBtn");

    let selectedUsers = [];

    // Function to fetch users and render them
    const fetchAndRenderUsers = async () => {
        try {
            const response = await fetch("/get-users"); // Your backend endpoint
            if (!response.ok) {
                throw new Error("Network response was not ok");
            }
            const users = await response.json();
            console.log(users);
            // Clear the current list
            usersListElement.innerHTML = "";

            // Populate the list with users from the backend
            Object.entries(users).forEach((user) => {
                const userItem = document.createElement("li");
                userItem.innerHTML = `<input type="checkbox" data-username="${user[0]}" /> ${user[0]} (${user[1]})`;
                usersListElement.appendChild(userItem);
            });
        } catch (error) {
            console.error("Failed to fetch users:", error);
            usersListElement.innerHTML = "<li>Failed to load users.</li>";
        }
    };

    // Function to update the list of selected users
    const updateSelectedUsers = () => {
        selectedUsers = [];
        const checkboxes = usersListElement.querySelectorAll(
            'input[type="checkbox"]:checked'
        );
        checkboxes.forEach((checkbox) => {
            selectedUsers.push(checkbox.dataset.username);
        });

        if (selectedUsers.length > 0) {
            selectedUsersTitle.textContent = `Selected: ${selectedUsers.join(
                ", "
            )}`;
        } else {
            selectedUsersTitle.textContent =
                "Select users to perform an action.";
        }
    };

    // Function to perform an action on selected users
    const performAction = async (action, details = {}) => {
        if (selectedUsers.length === 0) {
            alert("Please select at least one user.");
            return;
        }

        try {
            const response = await fetch(`/admin/${action}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ users: selectedUsers, ...details }),
            });

            if (response.ok) {
                alert(`Action '${action}' successful.`);
                fetchAndRenderUsers(); // Refresh the list after the action
            } else {
                const errorData = await response.json();
                alert(`Error: ${errorData.message}`);
            }
        } catch (error) {
            console.error(`Failed to perform action '${action}':`, error);
        }
    };
    const performActionNoUser = async (action, details = {}) => {
        try {
            const response = await fetch(`/admin/${action}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(details),
            });

            if (response.ok) {
                fetchAndRenderUsers(); // Refresh the list after the action
            } else {
                const errorData = await response.json();
                alert(`Error: ${errorData.message}`);
            }
        } catch (error) {
            console.error(`Failed to perform action '${action}':`, error);
        }
    };

    // Event Listeners
    refreshBtn.addEventListener("click", fetchAndRenderUsers);
    usersListElement.addEventListener("change", updateSelectedUsers);

    // --- Wire up all your action buttons ---
    kickBtn.addEventListener("click", () => performAction("kick"));
    document
        .getElementById("1dayBanBtn")
        .addEventListener("click", () =>
            performAction("ban", { duration: "1d" })
        );
    document
        .getElementById("1weekBanBtn")
        .addEventListener("click", () =>
            performAction("ban", { duration: "7d" })
        );
    document
        .getElementById("IPBanBtn")
        .addEventListener("click", () => performAction("ip-ban"));

    jumpscareBtn.addEventListener("click", () => performAction("jumpscare"));

    crashBtn.addEventListener("click", () =>
        alert(
            "The crash command has not been completed yet. Please check back later!"
        )
    );

    // Global
    resetChatBtn.addEventListener("click", () =>
        performActionNoUser("reset-chat")
    );
    reloadAllUsersBtn.addEventListener("click", () =>
        performActionNoUser("reload-all")
    );
    cloakAllUsersBtn.addEventListener("click", () =>
        performActionNoUser("cloak-all")
    );

    // Initial load
    fetchAndRenderUsers();
});
